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
        "note": "Strands run through every stage; the learning objectives change by stage. "
                "The children are the framework's published sub-strands, which it identifies "
                "by reporting code rather than by number — Rw, Rv, Rg and so on. A full "
                "objective code combines stage, sub-strand and sequence: 8Rw.01.",
        "topics": [
            ("1", "Reading", [
                ("1.Rw", "Word structure (phonics)"),
                ("1.Rv", "Vocabulary and language"),
                ("1.Rg", "Grammar and punctuation"),
                ("1.Rs", "Structure of texts"),
                ("1.Ri", "Interpretation of texts"),
                ("1.Ra", "Appreciation and reflection"),
            ]),
            ("2", "Writing", [
                ("2.Ww", "Word structure (spelling)"),
                ("2.Wv", "Vocabulary and language"),
                ("2.Wg", "Grammar and punctuation"),
                ("2.Ws", "Structure of texts"),
                ("2.Wc", "Creation of texts"),
                ("2.Wp", "Presentation and reflection"),
            ]),
            ("3", "Speaking and Listening", [
                ("3.SLm", "Making yourself understood"),
                ("3.SLs", "Showing understanding"),
                ("3.SLg", "Group work and discussion"),
                ("3.SLp", "Performance"),
                ("3.SLr", "Reflection and evaluation"),
            ]),
        ],
    },
    ("MATH", STAGE_LS): {
        "source": "Cambridge Lower Secondary Mathematics 0862 curriculum framework (v2, 2021)",
        "note": "Thinking and Working Mathematically is embedded across all four strands. 9 sub-strands seeded, with the framework's reporting codes (Ni, Np, Nf …).",
        "topics": [
            ("1", "Number", [
                ("1.Ni", "Integers, powers and roots"),
                ("1.Np", "Place value, ordering and rounding"),
                ("1.Nf", "Fractions, decimals, percentages, ratio and proportion"),
            ]),
            ("2", "Algebra", [
                ("2.Ae", "Expressions, equations and formulae"),
                ("2.As", "Sequences, functions and graphs"),
            ]),
            ("3", "Geometry and Measure", [
                ("3.Gg", "Geometrical reasoning, shapes and measurements"),
                ("3.Gp", "Position and transformation"),
            ]),
            ("4", "Statistics and Probability", [
                ("4.Ss", "Statistics"),
                ("4.Sp", "Probability"),
            ]),
        ],
    },
    ("SCI", STAGE_LS): {
        "source": "Cambridge Lower Secondary Science 0893 curriculum framework (v1, 2020)",
        "note": "16 sub-strands seeded. Science in Context publishes none — it is a single strand coded SIC — so it stays flat.",
        "topics": [
            ("1", "Thinking and Working Scientifically", [
                ("1.TWSm", "Models and representations"),
                ("1.TWSp", "Scientific enquiry: purpose and planning"),
                ("1.TWSc", "Carrying out scientific enquiry"),
                ("1.TWSa", "Scientific enquiry: analysis, evaluation and conclusions"),
            ]),
            ("2", "Biology", [
                ("2.Bs", "Structure and function"),
                ("2.Bp", "Life processes"),
                ("2.Be", "Ecosystems"),
            ]),
            ("3", "Chemistry", [
                ("3.Cm", "Materials and their structure"),
                ("3.Cp", "Properties of materials"),
                ("3.Cc", "Changes to materials"),
            ]),
            ("4", "Physics", [
                ("4.Pf", "Forces and energy"),
                ("4.Ps", "Light and sound"),
                ("4.Pe", "Electricity and magnetism"),
            ]),
            ("5", "Earth and Space", [
                ("5.ESp", "Planet Earth"),
                ("5.ESc", "Cycles on Earth"),
                ("5.ESs", "Earth in space"),
            ]),
            ("6", "Science in Context"),
        ],
    },
    ("CS", STAGE_LS): {
        "source": "Cambridge Lower Secondary Computing 0860 curriculum framework (v2.0, 2022)",
        "note": "Computing has no Checkpoint test, unlike English, Mathematics and Science. The framework also publishes no sub-strands: its five strands carry reporting codes (CT, P, MD, DC, CS) and objectives hang directly off them, so the strands stay flat.",
        "topics": [("1", "Computational Thinking"), ("2", "Programming"), ("3", "Managing Data"),
                   ("4", "Networks and Digital Communication"), ("5", "Computer Systems")],
    },
    ("GP", STAGE_LS): {
        "source": "Cambridge Lower Secondary Global Perspectives 1129 curriculum framework",
        "note": "18 sub-strands seeded. The framework names them but prints no reporting codes for them, unlike English, Mathematics and Science.",
        "topics": [
            ("1", "Research", [
                ("1.1", "Constructing research questions"),
                ("1.2", "Information skills"),
                ("1.3", "Conducting research"),
                ("1.4", "Recording findings"),
            ]),
            ("2", "Analysis", [
                ("2.1", "Identifying perspectives"),
                ("2.2", "Interpreting data"),
                ("2.3", "Making connections"),
                ("2.4", "Solving problems"),
            ]),
            ("3", "Evaluation", [
                ("3.1", "Evaluating sources"),
                ("3.2", "Evaluating arguments"),
            ]),
            ("4", "Reflection", [
                ("4.1", "Personal contribution"),
                ("4.2", "Teamwork"),
                ("4.3", "Personal viewpoints"),
                ("4.4", "Personal learning"),
            ]),
            ("5", "Collaboration", [
                ("5.1", "Cooperation and interdependence"),
                ("5.2", "Engaging in teamwork"),
            ]),
            ("6", "Communication", [
                ("6.1", "Communicating information"),
                ("6.2", "Listening and responding"),
            ]),
        ],
    },

    # --- Cambridge O Level, 2026 series -------------------------------
    ("PHY", STAGE_OL): {
        "source": "Cambridge O Level Physics 5054 syllabus 2026-2028 (697324)",
        "note": "25 sub-topics seeded. The syllabus also numbers a third level (1.5.1, 4.5.1 and so on); only the second level is seeded.",
        "topics": [
            ("1", "Motion, forces and energy", [
                ("1.1", "Physical quantities and measurement techniques"),
                ("1.2", "Motion"),
                ("1.3", "Mass and weight"),
                ("1.4", "Density"),
                ("1.5", "Forces"),
                ("1.6", "Momentum"),
                ("1.7", "Energy, work and power"),
                ("1.8", "Pressure"),
            ]),
            ("2", "Thermal physics", [
                ("2.1", "Kinetic particle model of matter"),
                ("2.2", "Thermal properties and temperature"),
                ("2.3", "Transfer of thermal energy"),
            ]),
            ("3", "Waves", [
                ("3.1", "General properties of waves"),
                ("3.2", "Light"),
                ("3.3", "Electromagnetic spectrum"),
                ("3.4", "Sound"),
            ]),
            ("4", "Electricity and magnetism", [
                ("4.1", "Simple magnetism and magnetic fields"),
                ("4.2", "Electrical quantities"),
                ("4.3", "Electric circuits"),
                ("4.4", "Practical electricity"),
                ("4.5", "Electromagnetic effects"),
                ("4.6", "Uses of an oscilloscope"),
            ]),
            ("5", "Nuclear physics", [
                ("5.1", "The nuclear model of the atom"),
                ("5.2", "Radioactivity"),
            ]),
            ("6", "Space physics", [
                ("6.1", "Earth and the Solar System"),
                ("6.2", "Stars and the Universe"),
            ]),
        ],
    },
    ("CHEM", STAGE_OL): {
        "source": "Cambridge O Level Chemistry 5070 syllabus 2026-2028 (697326)",
        "note": "49 sub-topics seeded, the syllabus's full second level.",
        "topics": [
            ("1", "States of matter", [
                ("1.1", "Solids, liquids and gases"),
                ("1.2", "Diffusion"),
            ]),
            ("2", "Atoms, elements and compounds", [
                ("2.1", "Elements, compounds and mixtures"),
                ("2.2", "Atomic structure and the Periodic Table"),
                ("2.3", "Isotopes"),
                ("2.4", "Ion and ionic bonds"),
                ("2.5", "Simple molecules and covalent bonds"),
                ("2.6", "Giant covalent structures"),
                ("2.7", "Metallic bonding"),
            ]),
            ("3", "Stoichiometry", [
                ("3.1", "Formulae"),
                ("3.2", "Relative masses of atoms and molecules"),
                ("3.3", "The mole and the Avogadro constant"),
            ]),
            ("4", "Electrochemistry", [
                ("4.1", "Electrolysis"),
                ("4.2", "Hydrogen–oxygen fuel cells"),
            ]),
            ("5", "Chemical energetics", [
                ("5.1", "Exothermic and endothermic reactions"),
            ]),
            ("6", "Chemical reactions", [
                ("6.1", "Physical and chemical changes"),
                ("6.2", "Rate of reaction"),
                ("6.3", "Reversible reactions and equilibrium"),
                ("6.4", "Redox"),
            ]),
            ("7", "Acids, bases and salts", [
                ("7.1", "The characteristic properties of acids and bases"),
                ("7.2", "Oxides"),
                ("7.3", "Preparation of salts"),
            ]),
            ("8", "The Periodic Table", [
                ("8.1", "Arrangement of elements"),
                ("8.2", "Group I properties"),
                ("8.3", "Group VII properties"),
                ("8.4", "Transition elements"),
                ("8.5", "Noble gases"),
            ]),
            ("9", "Metals", [
                ("9.1", "Properties of metals"),
                ("9.2", "Uses of metals"),
                ("9.3", "Alloys and their properties"),
                ("9.4", "Reactivity series"),
                ("9.5", "Corrosion of metals"),
                ("9.6", "Extraction of metals"),
            ]),
            ("10", "Chemistry of the environment", [
                ("10.1", "Water"),
                ("10.2", "Fertilisers"),
                ("10.3", "Air quality and climate"),
            ]),
            ("11", "Organic chemistry", [
                ("11.1", "Formulae, functional groups and terminology"),
                ("11.2", "Naming organic compounds"),
                ("11.3", "Fuels"),
                ("11.4", "Alkanes"),
                ("11.5", "Alkenes"),
                ("11.6", "Alcohols"),
                ("11.7", "Carboxylic acids"),
                ("11.8", "Polymers"),
            ]),
            ("12", "Experimental techniques and chemical analysis", [
                ("12.1", "Experimental design"),
                ("12.2", "Acid–base titrations"),
                ("12.3", "Chromatography"),
                ("12.4", "Separation and purification"),
                ("12.5", "Identification of ions and gases"),
            ]),
        ],
    },
    ("BIO", STAGE_OL): {
        "source": "Cambridge O Level Biology 5090 syllabus 2026-2028 (697330)",
        "note": "52 sub-topics seeded, the syllabus's full second level.",
        "topics": [
            ("1", "Cells", [
                ("1.1", "Cell structure and function"),
                ("1.2", "Specialised cells, tissues and organs"),
            ]),
            ("2", "Classification", [
                ("2.1", "Concept and use of a classification system"),
                ("2.2", "Features of organisms"),
            ]),
            ("3", "Movement into and out of cells", [
                ("3.1", "Diffusion and osmosis"),
                ("3.2", "Active transport"),
            ]),
            ("4", "Biological molecules", [
                ("4.1", "Biological molecules"),
            ]),
            ("5", "Enzymes", [
                ("5.1", "Enzyme action"),
                ("5.2", "Effects of temperature and pH"),
            ]),
            ("6", "Plant nutrition", [
                ("6.1", "Photosynthesis"),
                ("6.2", "Leaf structure"),
                ("6.3", "Mineral nutrition"),
            ]),
            ("7", "Transport in flowering plants", [
                ("7.1", "Uptake and transport of water and ions"),
                ("7.2", "Transpiration and translocation"),
            ]),
            ("8", "Human nutrition", [
                ("8.1", "Diet"),
                ("8.2", "Human digestive system"),
                ("8.3", "Absorption and assimilation"),
            ]),
            ("9", "Human gas exchange", [
                ("9.1", "Human gas exchange"),
            ]),
            ("10", "Respiration", [
                ("10.1", "Respiration"),
                ("10.2", "Aerobic respiration"),
                ("10.3", "Anaerobic respiration"),
            ]),
            ("11", "Transport in humans", [
                ("11.1", "Circulatory system"),
                ("11.2", "Heart"),
                ("11.3", "Blood vessels"),
                ("11.4", "Blood"),
            ]),
            ("12", "Disease and immunity", [
                ("12.1", "Disease"),
                ("12.2", "Antibiotics"),
                ("12.3", "Immunity"),
            ]),
            ("13", "Excretion", [
                ("13.1", "Excretion"),
                ("13.2", "Urinary system"),
            ]),
            ("14", "Coordination and control", [
                ("14.1", "Mammalian nervous system"),
                ("14.2", "Mammalian sense organs"),
                ("14.3", "Mammalian hormones"),
                ("14.4", "Homeostasis"),
                ("14.5", "Temperature control"),
                ("14.6", "Blood glucose control"),
            ]),
            ("15", "Coordination and response in plants", [
                ("15.1", "Coordination and response in plants"),
            ]),
            ("16", "Development of organisms and continuity of life", [
                ("16.1", "Nuclear division"),
                ("16.2", "Asexual and sexual reproduction"),
                ("16.3", "Sexual reproduction in plants"),
                ("16.4", "Sexual reproduction in humans"),
            ]),
            ("17", "Inheritance", [
                ("17.1", "Variation"),
                ("17.2", "DNA"),
                ("17.3", "Inheritance"),
                ("17.4", "Selection"),
            ]),
            ("18", "Biotechnology and genetic modification", [
                ("18.1", "Biotechnology"),
                ("18.2", "Genetic modification"),
            ]),
            ("19", "Relationships of organisms with one another and with the environment", [
                ("19.1", "Energy flow"),
                ("19.2", "Nutrient cycles"),
                ("19.3", "Ecosystems and biodiversity"),
                ("19.4", "Effects of humans on ecosystems"),
                ("19.5", "Conservation"),
            ]),
        ],
    },
    ("MATH", STAGE_OL): {
        "source": "Cambridge O Level Mathematics (Syllabus D) 4024 syllabus 2025-2027 (662480)",
        "note": "No separate 2026-2028 document; the 2025-2027 syllabus is in force for 2026. "
                "All 68 sub-topics are seeded verbatim and contiguous: 1.1-1.18, 2.1-2.12, "
                "3.1-3.7, 4.1-4.8, 5.1-5.5, 6.1-6.4, 7.1-7.4, 8.1-8.3, 9.1-9.7. Unlike IGCSE "
                "0580, 4024 has no differentiation sub-topic and no conditional probability.",
        "topics": [
            ("1", "Number", [
                ("1.1", "Types of number"),
                ("1.2", "Sets"),
                ("1.3", "Powers and roots"),
                ("1.4", "Fractions, decimals and percentages"),
                ("1.5", "Ordering"),
                ("1.6", "The four operations"),
                ("1.7", "Indices I"),
                ("1.8", "Standard form"),
                ("1.9", "Estimation"),
                ("1.10", "Limits of accuracy"),
                ("1.11", "Ratio and proportion"),
                ("1.12", "Rates"),
                ("1.13", "Percentages"),
                ("1.14", "Using a calculator"),
                ("1.15", "Time"),
                ("1.16", "Money"),
                ("1.17", "Exponential growth and decay"),
                ("1.18", "Surds"),
            ]),
            ("2", "Algebra and graphs", [
                ("2.1", "Introduction to algebra"),
                ("2.2", "Algebraic manipulation"),
                ("2.3", "Algebraic fractions"),
                ("2.4", "Indices II"),
                ("2.5", "Equations"),
                ("2.6", "Inequalities"),
                ("2.7", "Sequences"),
                ("2.8", "Proportion"),
                ("2.9", "Graphs in practical situations"),
                ("2.10", "Graphs of functions"),
                ("2.11", "Sketching curves"),
                ("2.12", "Functions"),
            ]),
            ("3", "Coordinate geometry", [
                ("3.1", "Coordinates"),
                ("3.2", "Drawing linear graphs"),
                ("3.3", "Gradient of linear graphs"),
                ("3.4", "Length and midpoint"),
                ("3.5", "Equations of linear graphs"),
                ("3.6", "Parallel lines"),
                ("3.7", "Perpendicular lines"),
            ]),
            ("4", "Geometry", [
                ("4.1", "Geometrical terms"),
                ("4.2", "Geometrical constructions"),
                ("4.3", "Scale drawings"),
                ("4.4", "Similarity"),
                ("4.5", "Symmetry"),
                ("4.6", "Angles"),
                ("4.7", "Circle theorems I"),
                ("4.8", "Circle theorems II"),
            ]),
            ("5", "Mensuration", [
                ("5.1", "Units of measure"),
                ("5.2", "Area and perimeter"),
                ("5.3", "Circles, arcs and sectors"),
                ("5.4", "Surface area and volume"),
                ("5.5", "Compound shapes and parts of shapes"),
            ]),
            ("6", "Trigonometry", [
                ("6.1", "Pythagoras' theorem"),
                ("6.2", "Right-angled triangles"),
                ("6.3", "Non-right-angled triangles"),
                ("6.4", "Pythagoras' theorem and trigonometry in 3D"),
            ]),
            ("7", "Transformations and vectors", [
                ("7.1", "Transformations"),
                ("7.2", "Vectors in two dimensions"),
                ("7.3", "Magnitude of a vector"),
                ("7.4", "Vector geometry"),
            ]),
            ("8", "Probability", [
                ("8.1", "Introduction to probability"),
                ("8.2", "Relative and expected frequencies"),
                ("8.3", "Probability of combined events"),
            ]),
            ("9", "Statistics", [
                ("9.1", "Classifying statistical data"),
                ("9.2", "Interpreting statistical data"),
                ("9.3", "Averages and measures of spread"),
                ("9.4", "Statistical charts and diagrams"),
                ("9.5", "Scatter diagrams"),
                ("9.6", "Cumulative frequency diagrams"),
                ("9.7", "Histograms"),
            ]),
        ],
    },
    ("ENG", STAGE_OL): {
        "source": "Cambridge O Level English Language 1123 syllabus 2024-2026 (634453)",
        "note": "A skills syllabus: subject content is two headings over an unnamed bullet "
                "list, so there is no topic list to seed. The children here are the "
                "syllabus's own assessment objectives — AO1 Reading (R1-R5) and AO2 Writing "
                "(W1-W5) — which are the only named skill breakdown Cambridge publishes for "
                "1123, and what marking is actually reported against. Assessment structure "
                "for reference: Paper 1 is Reading (Section A Comprehension and Use of "
                "Language, Section B Summary and Short response); Paper 2 is Writing "
                "(Section A Directed Writing, Section B Composition).",
        "topics": [
            ("1", "Reading", [
                ("1.R1", "Demonstrate understanding of explicit meanings"),
                ("1.R2", "Demonstrate understanding of implicit meanings and attitudes"),
                ("1.R3", "Analyse, evaluate and develop facts, ideas and opinions, using appropriate support from the text"),
                ("1.R4", "Demonstrate understanding of how writers achieve effects and influence readers"),
                ("1.R5", "Select and use information for specific purposes"),
            ]),
            ("2", "Writing", [
                ("2.W1", "Articulate experience and express what is thought, felt and imagined"),
                ("2.W2", "Organise and structure ideas and opinions for deliberate effect"),
                ("2.W3", "Use a range of vocabulary and sentence structures appropriate to context"),
                ("2.W4", "Use register appropriate to context"),
                ("2.W5", "Make accurate use of spelling, punctuation and grammar"),
            ]),
        ],
    },
    ("ISL", STAGE_OL): {
        "source": "Cambridge O Level Islamiyat 2058 syllabus 2026-2027 (697279)",
        "note": "Sub-topics deliberately not seeded. Only three of the eight sections publish named sub-headings, and the research pass returned inconsistent readings of exactly those (including the Appendix 1 list of set Qur'an passages). For scripture references in a live exam system that is not good enough, so the sections stay flat until the PDF can be read directly.",
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
        "note": "P1 = Paper 1 The history and culture of Pakistan; P2 = Paper 2 The environment of Pakistan. 41 sub-topics seeded: Paper 1's 16 Key Questions (numbered 1-16 in the syllabus, renumbered here within their section) and Paper 2's 25 lettered sub-headings.",
        "topics": [
            ("P1.1", "Cultural and historical background to the Pakistan Movement", [
                ("P1.1.1", "How successful were the religious thinkers in spreading Islam in the subcontinent during the 18th and 19th centuries?"),
                ("P1.1.2", "What were the causes and consequences of the decline of the Mughal Empire?"),
                ("P1.1.3", "What were the causes and consequences of the War of Independence 1857–58?"),
                ("P1.1.4", "How important was the work of Sir Syed Ahmad Khan to the development of the Pakistan Movement during the 19th century?"),
                ("P1.1.5", "To what extent have Urdu and regional languages contributed to the cultural development of Pakistan since 1947?"),
            ]),
            ("P1.2", "The emergence of Pakistan 1906–47", [
                ("P1.2.1", "How far did the Pakistan Movement develop during the early 20th century?"),
                ("P1.2.2", "How successful was the Khilafat Movement in advancing the cause of the Pakistan Movement?"),
                ("P1.2.3", "How successful was the Pakistan Movement in the years 1927 to 1939?"),
                ("P1.2.4", "How successful were attempts to find solutions to the problems facing the subcontinent in the years 1940 to 1947?"),
                ("P1.2.5", "How important were the contributions of Jinnah, Allama Iqbal and Rahmat Ali to the success of the Pakistan Movement to 1947?"),
            ]),
            ("P1.3", "Nationhood 1947–99", [
                ("P1.3.1", "How successful was the establishment of an independent nation between 1947 and 1948?"),
                ("P1.3.2", "How far did Pakistan achieve stability following the death of Jinnah?"),
                ("P1.3.3", "Why did East Pakistan seek and then form the independent state of Bangladesh?"),
                ("P1.3.4", "How successful was Pakistan in the twenty years following the 'Decade of Progress'?"),
                ("P1.3.5", "How effective were Pakistan's governments in the final decade of the 20th century?"),
                ("P1.3.6", "How important has Pakistan's role been in world affairs since 1947?"),
            ]),
            ("P2.1", "The land of Pakistan", [
                ("P2.1.a", "Location of Pakistan"),
                ("P2.1.b", "Location of administrative areas and cities"),
                ("P2.1.c", "The natural topography, including drainage"),
                ("P2.1.d", "Climate"),
            ]),
            ("P2.2", "Natural resources – an issue of sustainability", [
                ("P2.2.a", "Water"),
                ("P2.2.b", "Forests"),
                ("P2.2.c", "Mineral resources"),
                ("P2.2.d", "Fish"),
            ]),
            ("P2.3", "Power", [
                ("P2.3.a", "Sources"),
                ("P2.3.b", "Non-renewables"),
                ("P2.3.c", "Renewables"),
            ]),
            ("P2.4", "Agricultural development", [
                ("P2.4.a", "Agricultural systems"),
                ("P2.4.b", "Crops and livestock"),
                ("P2.4.c", "Factors affecting production"),
            ]),
            ("P2.5", "Industrial development", [
                ("P2.5.a", "Understanding common terms"),
                ("P2.5.b", "Secondary and tertiary industries"),
            ]),
            ("P2.6", "Trade", [
                ("P2.6.a", "Major exports and imports"),
                ("P2.6.b", "Pakistan's trading partners"),
            ]),
            ("P2.7", "Transport and telecommunications", [
                ("P2.7.a", "Internal transport"),
                ("P2.7.b", "International transport"),
                ("P2.7.c", "Telecommunications"),
            ]),
            ("P2.8", "Population and employment", [
                ("P2.8.a", "Structure and growth"),
                ("P2.8.b", "Movements of population"),
                ("P2.8.c", "Distribution and density of population"),
                ("P2.8.d", "Employment"),
            ]),
        ],
    },
    ("URD", STAGE_OL): {
        "source": "Cambridge O Level Urdu as a First Language 3247 syllabus 2025-2026 (664479)",
        "note": "The items here are already the syllabus's second level — the four Paper 1 topic areas and the three parts of Paper 2. Below them sit the set poetry and prose texts, which change by series and could not be read reliably (the syllabus prints them in Urdu script), so they are not seeded.",
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
        "note": "21 sub-topics seeded. Sections 7 Algorithm design and problem-solving, 9 Databases and 10 Boolean logic publish no numbered second level in the 2026-2028 syllabus — their content sits directly under the section heading — so they stay flat.",
        "topics": [
            ("1", "Data representation", [
                ("1.1", "Number systems"),
                ("1.2", "Text, sound and images"),
                ("1.3", "Data storage and compression"),
            ]),
            ("2", "Data transmission", [
                ("2.1", "Types and methods of data transmission"),
                ("2.2", "Methods of error detection"),
                ("2.3", "Encryption"),
            ]),
            ("3", "Hardware", [
                ("3.1", "Computer architecture"),
                ("3.2", "Input and output devices"),
                ("3.3", "Data storage"),
                ("3.4", "Network hardware"),
            ]),
            ("4", "Software", [
                ("4.1", "Types of software and interrupts"),
                ("4.2", "Types of programming language, translators and integrated development environments (IDEs)"),
            ]),
            ("5", "The internet and its uses", [
                ("5.1", "The internet and the world wide web"),
                ("5.2", "Digital currency"),
                ("5.3", "Cyber security"),
            ]),
            ("6", "Automated and emerging technologies", [
                ("6.1", "Automated systems"),
                ("6.2", "Robotics"),
                ("6.3", "Artificial intelligence"),
            ]),
            ("7", "Algorithm design and problem-solving"),
            ("8", "Programming", [
                ("8.1", "Programming concepts"),
                ("8.2", "Arrays"),
                ("8.3", "File handling"),
            ]),
            ("9", "Databases"),
            ("10", "Boolean logic"),
        ],
    },
    ("AMATH", STAGE_OL): {
        "source": "Cambridge O Level Additional Mathematics 4037 syllabus 2025-2027 (662720)",
        "note": "No second level to seed: 4037 prints no titled sub-topics. Each section is one table of numbered learning outcomes written as full sentences ('1.1 Understand the terms: function, domain, range …'), which is a level below sub-topics, so the sections stay flat.",
        "topics": [("1", "Functions"), ("2", "Quadratic functions"), ("3", "Factors of polynomials"),
                   ("4", "Equations, inequalities and graphs"), ("5", "Simultaneous equations"),
                   ("6", "Logarithmic and exponential functions"), ("7", "Straight-line graphs"),
                   ("8", "Coordinate geometry of the circle"), ("9", "Circular measure"),
                   ("10", "Trigonometry"), ("11", "Permutations and combinations"), ("12", "Series"),
                   ("13", "Vectors in two dimensions"), ("14", "Calculus")],
    },
    ("BUS", STAGE_OL): {
        "source": "Cambridge O Level Business Studies 7115 syllabus 2026 (697338)",
        "note": "25 sub-topics seeded, the syllabus's full second level.",
        "topics": [
            ("1", "Understanding business activity", [
                ("1.1", "Business activity"),
                ("1.2", "Classification of businesses"),
                ("1.3", "Enterprise, business growth and size"),
                ("1.4", "Types of business organisation"),
                ("1.5", "Business objectives and stakeholder objectives"),
            ]),
            ("2", "People in business", [
                ("2.1", "Motivating employees"),
                ("2.2", "Organisation and management"),
                ("2.3", "Recruitment, selection and training of employees"),
                ("2.4", "Internal and external communication"),
            ]),
            ("3", "Marketing", [
                ("3.1", "Marketing, competition and the customer"),
                ("3.2", "Market research"),
                ("3.3", "Marketing mix"),
                ("3.4", "Marketing strategy"),
            ]),
            ("4", "Operations management", [
                ("4.1", "Production of goods and services"),
                ("4.2", "Costs, scale of production and break-even analysis"),
                ("4.3", "Achieving quality production"),
                ("4.4", "Location decisions"),
            ]),
            ("5", "Financial information and decisions", [
                ("5.1", "Business finance: needs and sources"),
                ("5.2", "Cash-flow forecasting and working capital"),
                ("5.3", "Income statements"),
                ("5.4", "Statement of financial position"),
                ("5.5", "Analysis of accounts"),
            ]),
            ("6", "External influences on business activity", [
                ("6.1", "Economic issues"),
                ("6.2", "Environmental and ethical issues"),
                ("6.3", "Business and the international economy"),
            ]),
        ],
    },
    ("ACC", STAGE_OL): {
        "source": "Cambridge O Level Accounting 7707 syllabus 2026 (697340)",
        "note": "Principles of Accounts 7110 was withdrawn after November 2019 and replaced by 7707. 27 sub-topics seeded, the syllabus's full second level.",
        "topics": [
            ("1", "The fundamentals of accounting", [
                ("1.1", "The purpose of accounting"),
                ("1.2", "The accounting equation"),
            ]),
            ("2", "Sources and recording of data", [
                ("2.1", "The double entry system of book-keeping"),
                ("2.2", "Business documents"),
                ("2.3", "Books of prime entry"),
            ]),
            ("3", "Verification of accounting records", [
                ("3.1", "The trial balance"),
                ("3.2", "Correction of errors"),
                ("3.3", "Bank reconciliation"),
                ("3.4", "Control accounts"),
            ]),
            ("4", "Accounting procedures", [
                ("4.1", "Capital and revenue expenditure and receipts"),
                ("4.2", "Accounting for depreciation and disposal of non-current assets"),
                ("4.3", "Other payables and other receivables"),
                ("4.4", "Irrecoverable debts and provision for doubtful debts"),
                ("4.5", "Valuation of inventory"),
            ]),
            ("5", "Preparation of financial statements", [
                ("5.1", "Sole traders"),
                ("5.2", "Partnerships"),
                ("5.3", "Limited companies"),
                ("5.4", "Clubs and societies"),
                ("5.5", "Manufacturing accounts"),
                ("5.6", "Incomplete records"),
            ]),
            ("6", "Analysis and interpretation", [
                ("6.1", "Calculation and understanding of accounting ratios"),
                ("6.2", "Interpretation of accounting ratios"),
                ("6.3", "Inter-firm comparison"),
                ("6.4", "Interested parties"),
                ("6.5", "Limitations of accounting statements"),
            ]),
            ("7", "Accounting principles and policies", [
                ("7.1", "Accounting principles"),
                ("7.2", "Accounting policies"),
            ]),
        ],
    },
    ("ECON", STAGE_OL): {
        "source": "Cambridge O Level Economics 2281 syllabus 2026 (697295)",
        "note": "39 sub-topics seeded, the syllabus's full second level.",
        "topics": [
            ("1", "The basic economic problem", [
                ("1.1", "The nature of the economic problem"),
                ("1.2", "The factors of production"),
                ("1.3", "Opportunity cost"),
                ("1.4", "Production possibility curve (PPC) diagrams"),
            ]),
            ("2", "The allocation of resources", [
                ("2.1", "Microeconomics and macroeconomics"),
                ("2.2", "The role of markets in allocating resources"),
                ("2.3", "Demand"),
                ("2.4", "Supply"),
                ("2.5", "Price determination"),
                ("2.6", "Price changes"),
                ("2.7", "Price elasticity of demand (PED)"),
                ("2.8", "Price elasticity of supply (PES)"),
                ("2.9", "Market economic system"),
                ("2.10", "Market failure"),
                ("2.11", "Mixed economic system"),
            ]),
            ("3", "Microeconomic decision makers", [
                ("3.1", "Money and banking"),
                ("3.2", "Households"),
                ("3.3", "Workers"),
                ("3.4", "Trade unions"),
                ("3.5", "Firms"),
                ("3.6", "Firms and production"),
                ("3.7", "Firms' costs, revenue and objectives"),
                ("3.8", "Market structure"),
            ]),
            ("4", "Government and the macroeconomy", [
                ("4.1", "The role of government"),
                ("4.2", "The macroeconomic aims of government"),
                ("4.3", "Fiscal policy"),
                ("4.4", "Monetary policy"),
                ("4.5", "Supply-side policy"),
                ("4.6", "Economic growth"),
                ("4.7", "Employment and unemployment"),
                ("4.8", "Inflation and deflation"),
            ]),
            ("5", "Economic development", [
                ("5.1", "Living standards"),
                ("5.2", "Poverty"),
                ("5.3", "Population"),
                ("5.4", "Differences in economic development between countries"),
            ]),
            ("6", "International trade and globalisation", [
                ("6.1", "International specialisation"),
                ("6.2", "Globalisation, free trade and protection"),
                ("6.3", "Foreign exchange rates"),
                ("6.4", "Current account of balance of payments"),
            ]),
        ],
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
                "Candidates also take one depth study, most commonly Germany 1918-45. 26 focus points seeded beneath the six Key Questions. The syllabus numbers the Key Questions but not the focus points; the B1.1-style codes are ours. Under Key Question 5 the three items are introduced as case studies rather than focus points.",
        "topics": [
            ("B1", "Was the Treaty of Versailles fair?", [
                ("B1.1", "What were the motives and aims of the Big Three at Versailles?"),
                ("B1.2", "Why did the victors not get everything they wanted?"),
                ("B1.3", "What was the impact of the Treaty on Germany up to the end of 1923?"),
                ("B1.4", "Could the Treaty be justified at the time?"),
            ]),
            ("B2", "To what extent was the League of Nations a success?", [
                ("B2.1", "How far did weaknesses in the League's organisation and membership make failure inevitable?"),
                ("B2.2", "How successful were the League's attempts at peacekeeping in the 1920s?"),
                ("B2.3", "How important was the League's humanitarian work?"),
                ("B2.4", "How far did the Depression make the work of the League more difficult in the 1930s?"),
            ]),
            ("B3", "How far was Hitler's foreign policy to blame for the outbreak of war in Europe in 1939?", [
                ("B3.1", "What were the long-term consequences of the Treaty of Versailles?"),
                ("B3.2", "What were the consequences of the failures of the League of Nations in the 1930s?"),
                ("B3.3", "Was the policy of appeasement justified?"),
                ("B3.4", "How important was the Nazi–Soviet Pact?"),
                ("B3.5", "Why did Britain and France declare war on Germany in September 1939?"),
            ]),
            ("B4", "Who was to blame for the Cold War?", [
                ("B4.1", "Why did the US–Soviet alliance begin to break down in 1945?"),
                ("B4.2", "How had the USSR gained control of Eastern Europe by 1948?"),
                ("B4.3", "How did the United States react to Soviet expansionism?"),
                ("B4.4", "What were the consequences of the Berlin Blockade?"),
                ("B4.5", "Who was more to blame for starting the Cold War: the United States or the USSR?"),
            ]),
            ("B5", "How effectively did the United States contain the spread of communism?", [
                ("B5.1", "The United States and events in Korea, 1950–53"),
                ("B5.2", "The United States and events in Cuba, 1959–62"),
                ("B5.3", "American involvement in Vietnam, 1955–75"),
            ]),
            ("B6", "How secure was the USSR's control over Eastern Europe, 1948–c.1989?", [
                ("B6.1", "Why was there opposition to Soviet control in Hungary in 1956 and Czechoslovakia in 1968, and how did the USSR react to this opposition?"),
                ("B6.2", "How similar were events in Hungary in 1956 and in Czechoslovakia in 1968?"),
                ("B6.3", "Why was the Berlin Wall built in 1961?"),
                ("B6.4", "What was the significance of Solidarity in Poland for the decline of Soviet influence in Eastern Europe?"),
                ("B6.5", "How far was Gorbachev personally responsible for the collapse of Soviet control over Eastern Europe?"),
            ]),
        ],
    },
    ("ART", STAGE_OL): {
        "source": "Cambridge O Level Art & Design 6090 syllabus 2026 (696250)",
        "note": "Portfolio subject. Items 2-6 are the areas of study; item 1 is the common skills section. Each area does carry two headings — Skills and techniques, Knowledge and understanding — but they are identical in every area and are rubric headings rather than distinct content, so they are not seeded as sub-topics.",
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
