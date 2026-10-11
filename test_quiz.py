from utils.quiz_logic import level_from_score, points_for

for s in (0, 99, 100, 299, 300, 600, 1000):
    print(s, "->", level_from_score(s))

print(points_for(3, True), points_for(3, False))