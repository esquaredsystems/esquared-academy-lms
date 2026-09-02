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
# Grades. `level` doubles as the Cambridge stage number.
# ---------------------------------------------------------------------
GRADES = [
    {"short_name": "E1", "full_name": "Elementary 1", "level": 7, "is_terminal": False},
    {"short_name": "E2", "full_name": "Elementary 2", "level": 8, "is_terminal": False},
    {"short_name": "S1", "full_name": "Senior 1", "level": 9, "is_terminal": False},
    {"short_name": "S2", "full_name": "Senior 2", "level": 10, "is_terminal": False},
    {"short_name": "S3", "full_name": "Senior 3", "level": 11, "is_terminal": True},
]


# ---------------------------------------------------------------------
# Subject catalogue
# ---------------------------------------------------------------------
SUBJECTS = [
    {"short_name": "ENG", "full_name": "English Language", "id_number": "1123",
     "description": "Cambridge O Level English Language 1123; Lower Secondary English 0861."},
    {"short_name": "MATH", "full_name": "Mathematics", "id_number": "4024",
     "description": "Cambridge O Level Mathematics (Syllabus D) 4024; Lower Secondary Mathematics 0862."},
    {"short_name": "SCI", "full_name": "Science", "id_number": "0893",
     "description": "Cambridge Lower Secondary Science 0893. Splits into Physics, Chemistry and Biology at O Level."},
    {"short_name": "PHY", "full_name": "Physics", "id_number": "5054",
     "description": "Cambridge O Level Physics 5054."},
    {"short_name": "CHEM", "full_name": "Chemistry", "id_number": "5070",
     "description": "Cambridge O Level Chemistry 5070."},
    {"short_name": "BIO", "full_name": "Biology", "id_number": "5090",
     "description": "Cambridge O Level Biology 5090."},
    {"short_name": "ISL", "full_name": "Islamiyat", "id_number": "2058",
     "description": "Cambridge O Level Islamiyat 2058."},
    {"short_name": "PST", "full_name": "Pakistan Studies", "id_number": "2059",
     "description": "Cambridge O Level Pakistan Studies 2059."},
    {"short_name": "URD", "full_name": "Urdu (First Language)", "id_number": "3247",
     "description": "Cambridge O Level Urdu as a First Language 3247."},
    {"short_name": "CS", "full_name": "Computer Science", "id_number": "2210",
     "description": "Cambridge O Level Computer Science 2210; Lower Secondary Computing 0860."},
    {"short_name": "GP", "full_name": "Global Perspectives", "id_number": "1129",
     "description": "Cambridge Lower Secondary Global Perspectives 1129."},
    {"short_name": "AMATH", "full_name": "Additional Mathematics", "id_number": "4037",
     "description": "Cambridge O Level Additional Mathematics 4037."},
    {"short_name": "BUS", "full_name": "Business Studies", "id_number": "7115",
     "description": "Cambridge O Level Business Studies 7115."},
    {"short_name": "ACC", "full_name": "Accounting", "id_number": "7707",
     "description": "Cambridge O Level Accounting 7707. Replaced Principles of Accounts 7110, withdrawn after November 2019."},
    {"short_name": "ECON", "full_name": "Economics", "id_number": "2281",
     "description": "Cambridge O Level Economics 2281."},
    {"short_name": "GEO", "full_name": "Geography", "id_number": "2217",
     "description": "Cambridge O Level Geography 2217."},
    {"short_name": "HIST", "full_name": "History", "id_number": "2147",
     "description": "Cambridge O Level History 2147, Option B: international relations since 1919."},
    {"short_name": "ART", "full_name": "Art and Design", "id_number": "6090",
     "description": "Cambridge O Level Art & Design 6090. Portfolio subject; areas of study rather than examinable topics."},
]


# ---------------------------------------------------------------------
# Topics, by subject and stage.
# ---------------------------------------------------------------------
TOPICS = {
    ("ENG", STAGE_LS): {
        "source": "Cambridge Lower Secondary English 0861 curriculum framework (v1, 2020)",
        "note": "Strands run through every stage; the learning objectives change by stage.",
        "topics": [("1", "Reading"), ("2", "Writing"), ("3", "Speaking and Listening")],
    },
    ("MATH", STAGE_LS): {
        "source": "Cambridge Lower Secondary Mathematics 0862 curriculum framework (v2, 2021)",
        "note": "Thinking and Working Mathematically is embedded across all four strands.",
        "topics": [("1", "Number"), ("2", "Algebra"), ("3", "Geometry and Measure"),
                   ("4", "Statistics and Probability")],
    },
    ("SCI", STAGE_LS): {
        "source": "Cambridge Lower Secondary Science 0893 curriculum framework (v1, 2020)",
        "topics": [("1", "Thinking and Working Scientifically"), ("2", "Biology"),
                   ("3", "Chemistry"), ("4", "Physics"), ("5", "Earth and Space"),
                   ("6", "Science in Context")],
    },
    ("CS", STAGE_LS): {
        "source": "Cambridge Lower Secondary Computing 0860 curriculum framework (v2.0, 2022)",
        "note": "Computing has no Checkpoint test, unlike English, Mathematics and Science.",
        "topics": [("1", "Computational Thinking"), ("2", "Programming"), ("3", "Managing Data"),
                   ("4", "Networks and Digital Communication"), ("5", "Computer Systems")],
    },
    ("GP", STAGE_LS): {
        "source": "Cambridge Lower Secondary Global Perspectives 1129 curriculum framework",
        "topics": [("1", "Research"), ("2", "Analysis"), ("3", "Evaluation"),
                   ("4", "Reflection"), ("5", "Collaboration"), ("6", "Communication")],
    },

    # --- Cambridge O Level, 2026 series -------------------------------
    ("PHY", STAGE_OL): {
        "source": "Cambridge O Level Physics 5054 syllabus 2026-2028 (697324)",
        "topics": [("1", "Motion, forces and energy"), ("2", "Thermal physics"), ("3", "Waves"),
                   ("4", "Electricity and magnetism"), ("5", "Nuclear physics"),
                   ("6", "Space physics")],
    },
    ("CHEM", STAGE_OL): {
        "source": "Cambridge O Level Chemistry 5070 syllabus 2026-2028 (697326)",
        "topics": [("1", "States of matter"), ("2", "Atoms, elements and compounds"),
                   ("3", "Stoichiometry"), ("4", "Electrochemistry"), ("5", "Chemical energetics"),
                   ("6", "Chemical reactions"), ("7", "Acids, bases and salts"),
                   ("8", "The Periodic Table"), ("9", "Metals"),
                   ("10", "Chemistry of the environment"), ("11", "Organic chemistry"),
                   ("12", "Experimental techniques and chemical analysis")],
    },
    ("BIO", STAGE_OL): {
        "source": "Cambridge O Level Biology 5090 syllabus 2026-2028 (697330)",
        "topics": [("1", "Cells"), ("2", "Classification"), ("3", "Movement into and out of cells"),
                   ("4", "Biological molecules"), ("5", "Enzymes"), ("6", "Plant nutrition"),
                   ("7", "Transport in flowering plants"), ("8", "Human nutrition"),
                   ("9", "Human gas exchange"), ("10", "Respiration"), ("11", "Transport in humans"),
                   ("12", "Disease and immunity"), ("13", "Excretion"),
                   ("14", "Coordination and control"), ("15", "Coordination and response in plants"),
                   ("16", "Development of organisms and continuity of life"), ("17", "Inheritance"),
                   ("18", "Biotechnology and genetic modification"),
                   ("19", "Relationships of organisms with one another and with the environment")],
    },
    ("MATH", STAGE_OL): {
        "source": "Cambridge O Level Mathematics (Syllabus D) 4024 syllabus 2025-2027 (662480)",
        "note": "No separate 2026-2028 document; the 2025-2027 syllabus is in force for 2026.",
        "topics": [("1", "Number"), ("2", "Algebra and graphs"), ("3", "Coordinate geometry"),
                   ("4", "Geometry"), ("5", "Mensuration"), ("6", "Trigonometry"),
                   ("7", "Transformations and vectors"), ("8", "Probability"), ("9", "Statistics")],
    },
    ("ENG", STAGE_OL): {
        "source": "Cambridge O Level English Language 1123 syllabus 2024-2026 (634453)",
        "note": "Skills-based syllabus: subject content has only these two headings, no thematic topics.",
        "topics": [("1", "Reading"), ("2", "Writing")],
    },
    ("ISL", STAGE_OL): {
        "source": "Cambridge O Level Islamiyat 2058 syllabus 2026-2027 (697279)",
        "topics": [("P1.1", "Major themes of the Qur'an"),
                   ("P1.2", "The history and importance of the Qur'an"),
                   ("P1.3", "The life and importance of the Prophet Muhammad (pbuh)"),
                   ("P1.4", "The first Islamic community"),
                   ("P2.1", "Major teachings in the Hadiths of the Prophet"),
                   ("P2.2", "The history and importance of the Hadiths"),
                   ("P2.3", "The period of rule of the Rightly Guided Caliphs and their importance as leaders"),
                   ("P2.4", "The Articles of Faith and the Pillars of Islam")],
    },
    ("PST", STAGE_OL): {
        "source": "Cambridge O Level Pakistan Studies 2059 syllabus 2026 (697282)",
        "note": "P1 = Paper 1 The history and culture of Pakistan; P2 = Paper 2 The environment of Pakistan.",
        "topics": [("P1.1", "Cultural and historical background to the Pakistan Movement"),
                   ("P1.2", "The emergence of Pakistan 1906–47"),
                   ("P1.3", "Nationhood 1947–99"),
                   ("P2.1", "The land of Pakistan"),
                   ("P2.2", "Natural resources – an issue of sustainability"),
                   ("P2.3", "Power"),
                   ("P2.4", "Agricultural development"),
                   ("P2.5", "Industrial development"),
                   ("P2.6", "Trade"),
                   ("P2.7", "Transport and telecommunications"),
                   ("P2.8", "Population and employment")],
    },
    ("URD", STAGE_OL): {
        "source": "Cambridge O Level Urdu as a First Language 3247 syllabus 2025-2026 (664479)",
        "note": "No formal subject content chapter. P1 items are the Paper 1 topic areas; "
                "P2 items are the three parts of Paper 2 Texts, whose set texts change by series.",
        "topics": [("P1.1", "Health and fitness: e.g. food and diet, sport"),
                   ("P1.2", "The world of youth: e.g. music, traditional and modern culture, technology, fashion, family"),
                   ("P1.3", "Education and training: e.g. school and college, work, professions"),
                   ("P1.4", "The world we live in: e.g. current affairs, the environment, travel and tourism, the media"),
                   ("P2.1", "Part 1 Unseen Passage"),
                   ("P2.2", "Part 2 Poetry"),
                   ("P2.3", "Part 3 Prose")],
    },
    ("CS", STAGE_OL): {
        "source": "Cambridge O Level Computer Science 2210 syllabus 2026-2028 (697287)",
        "topics": [("1", "Data representation"), ("2", "Data transmission"), ("3", "Hardware"),
                   ("4", "Software"), ("5", "The internet and its uses"),
                   ("6", "Automated and emerging technologies"),
                   ("7", "Algorithm design and problem-solving"), ("8", "Programming"),
                   ("9", "Databases"), ("10", "Boolean logic")],
    },
    ("AMATH", STAGE_OL): {
        "source": "Cambridge O Level Additional Mathematics 4037 syllabus 2025-2027 (662720)",
        "topics": [("1", "Functions"), ("2", "Quadratic functions"), ("3", "Factors of polynomials"),
                   ("4", "Equations, inequalities and graphs"), ("5", "Simultaneous equations"),
                   ("6", "Logarithmic and exponential functions"), ("7", "Straight-line graphs"),
                   ("8", "Coordinate geometry of the circle"), ("9", "Circular measure"),
                   ("10", "Trigonometry"), ("11", "Permutations and combinations"), ("12", "Series"),
                   ("13", "Vectors in two dimensions"), ("14", "Calculus")],
    },
    ("BUS", STAGE_OL): {
        "source": "Cambridge O Level Business Studies 7115 syllabus 2026 (697338)",
        "topics": [("1", "Understanding business activity"), ("2", "People in business"),
                   ("3", "Marketing"), ("4", "Operations management"),
                   ("5", "Financial information and decisions"),
                   ("6", "External influences on business activity")],
    },
    ("ACC", STAGE_OL): {
        "source": "Cambridge O Level Accounting 7707 syllabus 2026 (697340)",
        "note": "Principles of Accounts 7110 was withdrawn after November 2019 and replaced by 7707.",
        "topics": [("1", "The fundamentals of accounting"), ("2", "Sources and recording of data"),
                   ("3", "Verification of accounting records"), ("4", "Accounting procedures"),
                   ("5", "Preparation of financial statements"), ("6", "Analysis and interpretation"),
                   ("7", "Accounting principles and policies")],
    },
    ("ECON", STAGE_OL): {
        "source": "Cambridge O Level Economics 2281 syllabus 2026 (697295)",
        "topics": [("1", "The basic economic problem"), ("2", "The allocation of resources"),
                   ("3", "Microeconomic decision makers"), ("4", "Government and the macroeconomy"),
                   ("5", "Economic development"), ("6", "International trade and globalisation")],
    },
    ("GEO", STAGE_OL): {
        "source": "Cambridge O Level Geography 2217 syllabus 2026 (697292)",
        "note": "The only O Level syllabus here that publishes its sub-topics as a "
                "numbered list, so they are seeded as children.",
        "topics": [
            ("1", "Theme 1: Population and settlement", [
                ("1.1", "Population dynamics"),
                ("1.2", "Migration"),
                ("1.3", "Population structure"),
                ("1.4", "Population density and distribution"),
                ("1.5", "Settlements (rural and urban) and service provision"),
                ("1.6", "Urban settlements"),
                ("1.7", "Urbanisation"),
            ]),
            ("2", "Theme 2: The natural environment", [
                ("2.1", "Earthquakes and volcanoes"),
                ("2.2", "Rivers"),
                ("2.3", "Coasts"),
                ("2.4", "Weather"),
                ("2.5", "Climate and natural vegetation"),
            ]),
            ("3", "Theme 3: Economic development", [
                ("3.1", "Development"),
                ("3.2", "Food production"),
                ("3.3", "Industry"),
                ("3.4", "Tourism"),
                ("3.5", "Energy"),
                ("3.6", "Water"),
                ("3.7", "Environmental risks of economic development"),
            ]),
        ],
    },
    ("HIST", STAGE_OL): {
        "source": "Cambridge O Level History 2147 syllabus 2024-2026 (649640)",
        "note": "Option B, the twentieth century core content taken by Pakistani centres. "
                "Candidates also take one depth study, most commonly Germany 1918-45.",
        "topics": [("B1", "Was the Treaty of Versailles fair?"),
                   ("B2", "To what extent was the League of Nations a success?"),
                   ("B3", "How far was Hitler's foreign policy to blame for the outbreak of war in Europe in 1939?"),
                   ("B4", "Who was to blame for the Cold War?"),
                   ("B5", "How effectively did the United States contain the spread of communism?"),
                   ("B6", "How secure was the USSR's control over Eastern Europe, 1948–c.1989?")],
    },
    ("ART", STAGE_OL): {
        "source": "Cambridge O Level Art & Design 6090 syllabus 2026 (696250)",
        "note": "Portfolio subject. Items 2-6 are the areas of study; item 1 is the common skills section.",
        "topics": [("1", "Skills and understanding common to all areas of study"),
                   ("2", "Painting and related media"), ("3", "Graphic communication"),
                   ("4", "Three-dimensional design"), ("5", "Textiles and fashion"),
                   ("6", "Photography")],
    },
}


# ---------------------------------------------------------------------
# What each grade studies. (subject, stage, is_core)
# ---------------------------------------------------------------------
LS_CORE = [("ENG", STAGE_LS, True), ("MATH", STAGE_LS, True), ("SCI", STAGE_LS, True),
           ("CS", STAGE_LS, True), ("GP", STAGE_LS, True),
           ("ISL", STAGE_LS, True), ("URD", STAGE_LS, True)]

OL_CORE = [("ENG", STAGE_OL, True), ("MATH", STAGE_OL, True), ("ISL", STAGE_OL, True),
           ("PST", STAGE_OL, True), ("URD", STAGE_OL, True)]

OL_SCIENCES = [("PHY", STAGE_OL, True), ("CHEM", STAGE_OL, True), ("BIO", STAGE_OL, True),
               ("CS", STAGE_OL, True)]

OL_ELECTIVES = [("PHY", STAGE_OL, False), ("CHEM", STAGE_OL, False), ("BIO", STAGE_OL, False),
                ("CS", STAGE_OL, False), ("AMATH", STAGE_OL, False), ("BUS", STAGE_OL, False),
                ("ACC", STAGE_OL, False), ("ECON", STAGE_OL, False), ("GEO", STAGE_OL, False),
                ("HIST", STAGE_OL, False), ("ART", STAGE_OL, False)]

CURRICULUM = {
    "E1": LS_CORE,
    "E2": LS_CORE,
    "S1": OL_CORE + OL_SCIENCES,
    "S2": OL_CORE + OL_SCIENCES,
    "S3": OL_CORE + OL_ELECTIVES,
}
