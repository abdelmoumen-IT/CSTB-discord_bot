from database.connection import get_pool

async def get_modules() -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, name, slug FROM modules ORDER BY position, name"
    )
    return [dict(r) for r in rows]


async def get_categories(module_id: int) -> list[dict]:
    rows = await get_pool().fetch(
        """
        SELECT id, name, slug
        FROM categories
        WHERE module_id = $1
        ORDER BY position, name
        """,
        module_id,
    )
    return [dict(r) for r in rows]


async def get_resources(category_id: int) -> list[dict]:
    rows = await get_pool().fetch(
        """
        SELECT id, title, description, file_url, storage_ref, file_name
        FROM resources
        WHERE category_id = $1
        ORDER BY created_at DESC
        """,
        category_id,
    )
    return [dict(r) for r in rows]

async def add_resource(category_id: int, title: str, description: str | None,
                       storage_ref: str, file_name: str, created_by: int) -> int:
    return await get_pool().fetchval(
        """
        INSERT INTO resources (category_id, title, description, storage_ref, file_name, created_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        category_id, title, description, storage_ref, file_name, created_by,
    )

async def delete_resource(resource_id: int) -> dict | None:
    row = await get_pool().fetchrow(
        "DELETE FROM resources WHERE id = $1 RETURNING id, title, storage_ref",
        resource_id,
    )
    return dict(row) if row else None

async def add_module(name: str, slug: str) -> int:
    return await get_pool().fetchval(
        """
        INSERT INTO modules (name, slug, position)
        VALUES ($1, $2, COALESCE((SELECT MAX(position) FROM modules), 0) + 1)
        RETURNING id
        """,
        name, slug,
    )


async def add_category(module_id: int, name: str, slug: str) -> int:
    return await get_pool().fetchval(
        """
        INSERT INTO categories (module_id, name, slug, position)
        VALUES ($1, $2, $3,
                COALESCE((SELECT MAX(position) FROM categories WHERE module_id = $1), 0) + 1)
        RETURNING id
        """,
        module_id, name, slug,
    )

async def rename_module(module_id: int, name: str) -> bool:
    row = await get_pool().fetchval(
        "UPDATE modules SET name = $2 WHERE id = $1 RETURNING id", module_id, name
    )
    return row is not None


async def rename_category(category_id: int, name: str) -> bool:
    row = await get_pool().fetchval(
        "UPDATE categories SET name = $2 WHERE id = $1 RETURNING id", category_id, name
    )
    return row is not None


async def delete_module(module_id: int) -> bool:
    row = await get_pool().fetchval(
        "DELETE FROM modules WHERE id = $1 RETURNING id", module_id
    )
    return row is not None


async def delete_category(category_id: int) -> bool:
    row = await get_pool().fetchval(
        "DELETE FROM categories WHERE id = $1 RETURNING id", category_id
    )
    return row is not None

async def mark_welcomed(user_id: int) -> bool:
    row = await get_pool().fetchval(
        "INSERT INTO welcomed_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING RETURNING user_id",
        user_id,
    )
    return row is not None