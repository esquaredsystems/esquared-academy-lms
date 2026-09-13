"""
Curriculum data
Two stages are represented, and a subject can carry topics for both:
    LS   Cambridge Lower Secondary curriculum framework (stages 7-9)
    OL   Cambridge O Level syllabus (2026 series)

E1 and E2 are Lower Secondary stages 7 and 8. S1, S2 and S3 run the O Level programme over three years,
with S3 terminal, where subjects differ per student.
"""

STAGE_LS = "LS"
STAGE_OL = "OL"

# ---------------------------------------------------------------------
# Classes. `level` doubles as the Cambridge stage number.
# ---------------------------------------------------------------------
ACADEMY_CLASSES = [
    {"short_name": "E1", "full_name": "Elementary 1", "level": 1, "is_terminal": False},
    {"short_name": "E2", "full_name": "Elementary 2", "level": 2, "is_terminal": False},
    {"short_name": "S1", "full_name": "Senior 1", "level": 3, "is_terminal": False},
    {"short_name": "S2", "full_name": "Senior 2", "level": 4, "is_terminal": False},
    {"short_name": "S3", "full_name": "Senior 3", "level": 5, "is_terminal": True},
]

SUBJECTS = []
TOPICS = {}
CURRICULUM = {}
