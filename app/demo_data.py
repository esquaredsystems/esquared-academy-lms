"""
Demo data: three teachers and twenty students, Karachi names.

Everything here is fictional. Rows are tagged with a DEMO- prefix in their
`staff_no` / `admission_no`, which is how the demo page finds them again to
remove them — voiding, never deleting, like everything else in the system.

Placement follows the school's own rule: E1 through S2 take the whole core
set for their class, and only S3 students choose. Each S3 student below
takes the five core subjects plus the electives listed against them.
"""

PREFIX = "DEMO-"

#: Password for the demo teacher logins. Development only.
DEMO_PASSWORD = "demo12345"

#: Guardian numbers are built from this Karachi mobile prefix.
PHONE_PREFIX = "+92 300 55"

# ---------------------------------------------------------------------
# Marking. The demo fills in topic results so the knowledge map and the
# completion percentages have something to show: part of each subject
# marked, the rest still open, and students who are stronger in some
# subjects than others.
#
# Everything is derived from the admission number, so the same student
# gets the same marks every time the demo is loaded.
# ---------------------------------------------------------------------

#: How able a demo student is, as a mark out of a hundred, before subject
#: variation. Drawn from this range.
ABILITY_RANGE = (54, 88)

#: How much of each subject has been assessed by now.
COVERAGE_RANGE = (0.30, 0.80)

#: Spread of one student's marks around their ability, in points.
MARK_SPREAD = 11


# ---------------------------------------------------------------------
# Staff. One teacher covers several subjects, as they do in a small
# school. `teaches` lists subject short names; the seeder attaches each
# teacher to every syllabus running that subject this year.
# ---------------------------------------------------------------------
TEACHERS = [
    {
        "staff_no": f"{PREFIX}T01",
        "first_name": "Farah",
        "last_name": "Siddiqui",
        "username": "f.siddiqui",
        "email": "f.siddiqui@esquared.example",
        "teaches": ["ENG", "URD", "PST"],
    },
    {
        "staff_no": f"{PREFIX}T02",
        "first_name": "Imran",
        "last_name": "Qureshi",
        "username": "i.qureshi",
        "email": "i.qureshi@esquared.example",
        "teaches": ["MATH", "AMATH", "PHY", "CS"],
    },
    {
        "staff_no": f"{PREFIX}T03",
        "first_name": "Naila",
        "last_name": "Ansari",
        "username": "n.ansari",
        "email": "n.ansari@esquared.example",
        "teaches": ["SCI", "CHEM", "BIO", "ISL", "GP"],
    },
]


# ---------------------------------------------------------------------
# Students, four per class. `electives` applies only in S3, the terminal
# class; it is ignored anywhere else, where everyone takes the core set.
# ---------------------------------------------------------------------
STUDENTS = [
    # E1
    {"admission_no": f"{PREFIX}S01", "first_name": "Zoya", "last_name": "Kazmi",
     "academy_class": "E1", "guardian_name": "Adnan Kazmi"},
    {"admission_no": f"{PREFIX}S02", "first_name": "Hamza", "last_name": "Memon",
     "academy_class": "E1", "guardian_name": "Rehana Memon"},
    {"admission_no": f"{PREFIX}S03", "first_name": "Alishba", "last_name": "Rizvi",
     "academy_class": "E1", "guardian_name": "Sarwar Rizvi"},
    {"admission_no": f"{PREFIX}S04", "first_name": "Ahmed", "last_name": "Sheikh",
     "academy_class": "E1", "guardian_name": "Nadia Sheikh"},

    # E2
    {"admission_no": f"{PREFIX}S05", "first_name": "Fatima", "last_name": "Jafri",
     "academy_class": "E2", "guardian_name": "Kashif Jafri"},
    {"admission_no": f"{PREFIX}S06", "first_name": "Bilal", "last_name": "Abbasi",
     "academy_class": "E2", "guardian_name": "Shazia Abbasi"},
    {"admission_no": f"{PREFIX}S07", "first_name": "Mahnoor", "last_name": "Baloch",
     "academy_class": "E2", "guardian_name": "Yousuf Baloch"},
    {"admission_no": f"{PREFIX}S08", "first_name": "Talha", "last_name": "Farooqui",
     "academy_class": "E2", "guardian_name": "Ambreen Farooqui"},

    # S1
    {"admission_no": f"{PREFIX}S09", "first_name": "Ayesha", "last_name": "Hashmi",
     "academy_class": "S1", "guardian_name": "Tariq Hashmi"},
    {"admission_no": f"{PREFIX}S10", "first_name": "Saad", "last_name": "Zuberi",
     "academy_class": "S1", "guardian_name": "Farzana Zuberi"},
    {"admission_no": f"{PREFIX}S11", "first_name": "Hina", "last_name": "Lakhani",
     "academy_class": "S1", "guardian_name": "Aslam Lakhani"},
    {"admission_no": f"{PREFIX}S12", "first_name": "Danish", "last_name": "Soomro",
     "academy_class": "S1", "guardian_name": "Rubina Soomro"},

    # S2
    {"admission_no": f"{PREFIX}S13", "first_name": "Sana", "last_name": "Ghouri",
     "academy_class": "S2", "guardian_name": "Javed Ghouri"},
    {"admission_no": f"{PREFIX}S14", "first_name": "Owais", "last_name": "Tirmizi",
     "academy_class": "S2", "guardian_name": "Sadia Tirmizi"},
    {"admission_no": f"{PREFIX}S15", "first_name": "Areeba", "last_name": "Naqvi",
     "academy_class": "S2", "guardian_name": "Mohsin Naqvi"},
    {"admission_no": f"{PREFIX}S16", "first_name": "Rayyan", "last_name": "Dossani",
     "academy_class": "S2", "guardian_name": "Nasreen Dossani"},

    # S3 — the terminal class, where subjects differ per student
    {"admission_no": f"{PREFIX}S17", "first_name": "Kiran", "last_name": "Merchant",
     "academy_class": "S3", "guardian_name": "Iqbal Merchant",
     "electives": ["PHY", "CHEM", "BIO"]},                 # pre-medical
    {"admission_no": f"{PREFIX}S18", "first_name": "Zain", "last_name": "Kapadia",
     "academy_class": "S3", "guardian_name": "Samina Kapadia",
     "electives": ["PHY", "CHEM", "AMATH", "CS"]},         # pre-engineering
    {"admission_no": f"{PREFIX}S19", "first_name": "Maryam", "last_name": "Alvi",
     "academy_class": "S3", "guardian_name": "Faisal Alvi",
     "electives": ["BUS", "ACC", "ECON"]},                 # commerce
    {"admission_no": f"{PREFIX}S20", "first_name": "Shahmir", "last_name": "Vohra",
     "academy_class": "S3", "guardian_name": "Uzma Vohra",
     "electives": ["GEO", "HIST", "ART", "CS"]},           # humanities
]
