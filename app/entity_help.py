"""
What each entity is, what it means here, and what its fields are for.

The admin shows this behind the "?" beside the add button on every change
list. Four parts per model:

    summary  what the row is, in one sentence
    role     where it sits in the system and what depends on it
    context  what it means at Esquared specifically — the local rule, the
             thing that would otherwise have to be explained in person
    fields   the attributes that carry meaning, and what each one decides.
             Obvious ones (names, descriptions) are left out; the ones
             people get wrong are in.

Every field named here must exist on the model — a test enforces it, so
this cannot drift as the models change. The audit block is documented once
in the admin's own Audit section rather than repeated on 33 entities.

Keyed by `model._meta.model_name`.
"""

ENTITY_HELP = {
    # -- people and placement ------------------------------------------
    "appuser": {
        "summary": "A login: staff, student or guardian.",
        "role": "Every audit column in the system points at one of these — whoever created, changed or voided a row. Roles are the groups an account belongs to.",
        "context": "A person may exist without an account. Students only need one if they sit papers online; guardians only if they check their child's records.",
        "fields": [
            ("username", "What they sign in with. Case-insensitively unique among live accounts."),
            ("groups", "Their roles. Administrator, Teacher, Examiner, Student, Guardian or Guest — this is what decides what they can reach."),
            ("is_staff", "May reach /admin/ at all. Every account here carries it, students included — the whole interface lives under /admin/ and Django's login refuses anyone without it. It is a door key, not a rank: what holds a student to their own rows is the Student role's narrow permissions plus the row scoping in app/access.py."),
            ("is_active", "Django's login switch. Turning it off blocks sign-in immediately."),
            ("suspended", "The school's own state, separate from is_active: on the roll but stood down."),
            ("id_number", "External identifier for imports and reports. Optional, unique when present."),
        ],
    },
    "academyclass": {
        "summary": "A class.",
        "role": "Students enrol into a class for a year; syllabi, cohorts, papers and registers all hang off it.",
        "context": "E1 and E2 are Lower Secondary (Cambridge stages 7–8). S1, S2 and S3 run the O Level programme. S3 is the terminal class — the only one where students take different subjects.",
        "fields": [
            ("level", "The Cambridge stage number: 7 and 8 for E1/E2, 9 to 11 for S1–S3. Unique, and what the classes sort by."),
            ("short_name", "E1, S3 — what staff type and what appears in lists."),
            ("is_terminal", "Marks the final class, where subjects differ per student. Only S3 has it."),
            ("capacity", "Places in the class. Optional, and not enforced — it is there for planning."),
            ("visible", "Hides the class from pickers without deleting it. Not the same as voiding."),
        ],
    },
    "student": {
        "summary": "A student, independent of the class they currently sit in.",
        "role": "The person record. Their placement each year is an Enrolment, so history survives when they move up.",
        "context": "Admission number is the identifier staff actually use. Guardian name and contact are the details on the record; a guardian's *access* is a separate Guardian link.",
        "fields": [
            ("admission_no", "The school's identifier. Unique among live records, and the field to search by."),
            ("user", "Their login, if they have one. Empty for students who never sit papers online."),
            ("first_name", "As printed on the national ID. Many names do not split, so everything but the final word belongs here."),
            ("last_name", "Optional. Leave it empty when the ID carries a single name."),
            ("email", "A guardian's address for a younger student, their own later. Not unique — siblings share one."),
            ("mobile", "Mobile number. Needed for a Cambridge entry."),
            ("address", "Residential address, as it should appear on an exam entry."),
            ("national_id", "CNIC, B-Form or passport number, exactly as printed. Optional at admission, required before an exam entry. Which document it is, and any second guardian contact, are recorded as attributes below rather than columns here."),
            ("guardian_name", "Contact detail only. It grants nobody any access."),
            ("guardian_contact", "The number the office rings. Also just a detail."),
            ("date_of_birth", "Used for reports and age checks; optional."),
            ("photo", "Their portrait. Square — the width must equal the height — and under 100 KB. Stored with the other pictures and shown as the avatar in lists."),
        ],
    },
    "studentattributetype": {
        "summary": "One typed optional property a student can carry, beyond the core columns.",
        "role": "Replaces fields like national_id_type and guardian_contact_2 that varied by document type or school policy: a new one is a data row, not a migration.",
        "context": "Set up once here, then filled in per student on the student's own change form.",
        "fields": [
            ("short_name", "The stable key code looks this up by. Set once — changing it orphans values stored under the old key."),
            ("datatype", "How the stored text is interpreted: text, yes/no, whole number, decimal, date or date+time."),
            ("datatype_config", "Datatype-specific configuration. For text, a '|'-separated list of allowed values acts as a closed choice set — this is how national_id_type's cnic/b_form/passport options are expressed."),
            ("min_occurs", "0 means optional. Not enforced by a database constraint."),
            ("max_occurs", "1 means single-valued, the normal case."),
            ("visible", "Hides the type from pickers without deleting it."),
        ],
    },
    "studentattribute": {
        "summary": "One student's value for one StudentAttributeType.",
        "role": "The optional-field data itself — what used to live in national_id_type/guardian_contact_2 columns.",
        "context": "The value is always stored as text (value_reference) and resolved to a real Python value through its attribute type's datatype.",
        "fields": [
            ("student", "The student this value belongs to."),
            ("attribute_type", "Which property this is — and therefore how value_reference is interpreted."),
            ("value_reference", "The value, as text. Read it through get_value() rather than directly."),
        ],
    },
    "timetableslot": {
        "summary": "One line of the weekly timetable: a subject, a class, a day and a period.",
        "role": "The pattern lessons are created from. It is a template, not a record of what happened.",
        "context": "Set once and changed rarely. A teacher swapping days edits that day's lesson, not this slot, so the weeks already taught stay true. Breaks are not modelled - only periods that are lessons appear here.",
        "fields": [
            ("syllabus", "The subject, class and year this slot teaches."),
            ("teacher", "Who normally teaches it. A lesson may name someone else."),
            ("period", "The period label, the same one registers use."),
        ],
    },
    "lesson": {
        "summary": "One class on one date - the row everything about that class hangs off.",
        "role": "Lecture material attaches to it, topics are planned and ticked off on it, and it is the unit the head reviews.",
        "context": "Drafted by the teacher, submitted, then approved by an Administrator. Nothing reaches students until it is approved. An empty 'date taught' means the lesson was never written up, which is what the compliance view looks for.",
        "fields": [
            ("slot", "The weekly slot this came from. Empty for a one-off lesson."),
            ("plan", "What will be taught. Prepared in advance; this is what the head reviews."),
            ("log", "Written after the lesson: what was actually covered, and anything the class needs."),
            ("date_taught", "Set when the teacher logs the lesson. Empty means it was never written up."),
            ("status", "Draft, submitted, approved, returned or retired."),
            ("review_comment", "Why it was returned. Review is for improving the lesson, not only gating it."),
        ],
    },
    "lessontopic": {
        "summary": "A topic a lesson plans to cover, and whether it actually was.",
        "role": "Planned is set when the lesson is written; covered when it is logged afterwards.",
        "context": "The gap between planned and covered is the useful signal - it is what 'pending topics' means on a student's view.",
        "fields": [
            ("planned", "The topic was meant to be taught in this lesson."),
            ("covered", "Ticked when the lesson is logged after teaching."),
        ],
    },
    "teacher": {
        "summary": "A member of teaching staff, tied to their login.",
        "role": "Teaching assignments connect a teacher to the syllabi they teach.",
        "context": "Staff number is the school identifier. Removing a teacher means voiding the record, never deleting it — their marking history references them.",
        "fields": [
            ("user", "The account they sign in with. Required — a teacher without a login cannot mark."),
            ("staff_no", "The school's identifier, unique among live records."),
            ("photo", "Their portrait, under the same two rules as a student's: square first, then under 100 KB."),
        ],
    },
    "enrolment": {
        "summary": "Places one student in one class for one academic year.",
        "role": "The row nearly everything year-scoped hangs off: subject choices, cohort membership, attendance.",
        "context": "A student can hold only one live enrolment per year. If one is wrong, void it and create the correction — the voided row keeps the audit trail and does not block the new one.",
        "fields": [
            ("academic_year", "A plain year number, 2026. Together with the student it is the uniqueness rule."),
            ("academy_class", "Which class they are in that year. Change of class mid-year means voiding this and creating another."),
            ("started_on", "When the placement began; defaults to today."),
            ("ended_on", "Set when a student leaves mid-year. Empty means still enrolled."),
            ("status", "Free text for the office: active, transferred, withdrawn."),
        ],
    },
    "guardianlink": {
        "summary": "Which students a guardian account may see.",
        "role": "The access relationship behind the Guardian role. Without a link here, a guardian account sees nothing.",
        "context": "Separate from the guardian name and phone number on the student record, which are contact details. This one grants sight of results and attendance.",
        "fields": [
            ("user", "The guardian's login. This is what turns a name into access."),
            ("student", "The ward. One link per student; a parent with three children has three links."),
            ("relationship", "father, mother, guardian, other. Shown on reports."),
            ("is_primary", "Who the school contacts first."),
            ("can_view_marks", "Lets a guardian see results as well as attendance."),
        ],
    },

    # -- curriculum ----------------------------------------------------
    "subject": {
        "summary": "A subject in the permanent catalogue.",
        "role": "Owns its topics; a syllabus offers it to a class in a year.",
        "context": "The catalogue is permanent — a subject not taught this year stays here. Its id number is the Cambridge syllabus code (4024, 5054, 2058 and so on).",
        "fields": [
            ("short_name", "ENG, PHY, AMATH. Unique, and what appears in compact lists."),
            ("id_number", "The Cambridge syllabus code: 4024 for Maths D, 5054 for Physics."),
            ("description_format", "How the description is written — plain, HTML or Markdown."),
            ("sort_order", "The order subjects appear in menus and reports."),
            ("visible", "Hides it from pickers without removing it from the catalogue."),
        ],
    },
    "topic": {
        "summary": "A section of a subject's syllabus.",
        "role": "The permanent topic catalogue. Questions are written against topics.",
        "context": "Topics nest: a syllabus section holds the things actually taught under it — Programming holds Loops and Conditions, Rivers holds Erosion and Deposition. Questions can be written against any level. Dropping a topic from a year means removing it from that year's syllabus, never deleting it here.",
        "fields": [
            ("subject", "The subject that owns it. A topic belongs to exactly one, and a parent must be in the same subject."),
            ("parent", "The topic this one sits under. Empty makes it a top-level syllabus section; setting it makes it a sub-topic. A topic cannot sit under its own descendant, and the tree stops at four levels."),
            ("short_name", "The syllabus's own section reference, prefixed by stage: LS- for Lower Secondary strands, OL- for O Level sections. Unique within the subject."),
            ("depth", "0 for a syllabus section, 1 for its children, and so on. Maintained automatically."),
            ("path", "Ancestor ids, root first. Maintained automatically, and what makes 'everything under this topic' a single query."),
            ("description", "Carries the source syllabus document the title was taken from."),
            ("sort_order", "Position among its siblings, not necessarily the teaching order — that lives on the syllabus."),
        ],
    },
    "syllabus": {
        "summary": "One subject, taught to one class, in one academic year.",
        "role": "Both the offering and the topic list for that run. Teaching assignments and student subject choices point here.",
        "context": "This is where a year's curriculum actually differs from the last. Core subjects are taken by everyone in the class; in S3 the non-core ones are chosen.",
        "fields": [
            ("subject", "What is taught."),
            ("academy_class", "Who it is taught to."),
            ("academic_year", "When. Subject, class and year together are unique — one syllabus per run."),
            ("is_core", "Everyone in the class takes it. Clear it for an S3 elective, which students then choose."),
            ("status", "draft while being built, published once teaching, retired afterwards."),
            ("date_published", "When it was published. Left empty on drafts."),
            ("pass_mark_pct", "The mark a topic result must reach to count as passed, 50% by default. It lives here rather than on each result, so moving the bar re-reads the whole year's marks without re-entering any of them."),
        ],
    },
    "syllabustopic": {
        "summary": "A topic's place on one year's syllabus, with its teaching order.",
        "role": "The link that lets a topic appear in 2026 and not in 2027 without disturbing the catalogue. Only top-level topics are listed; their children come with them.",
        "context": "Removing a row here drops the topic from that year only. The topic, and every question written against it, stays.",
        "fields": [
            ("sort_order", "The order it is taught. Unique within the syllabus — no two topics share a position."),
            ("weight_pct", "Share of the year's assessment, 0–100. Optional, and only used by reports."),
        ],
    },
    "studentsubject": {
        "summary": "A subject a particular student is taking.",
        "role": "Connects an enrolment to a syllabus.",
        "context": "In E1–S2 these follow automatically from the core syllabi. In S3 they are real choices, and this is where they are recorded.",
        "fields": [
            ("enrolment", "Which student, in which year. Going through the enrolment is what keeps the choice tied to the right year."),
            ("syllabus", "The subject run they are taking. One row per subject per student per year."),
        ],
    },
    "topicresult": {
        "summary": "Where one student stands on one topic of one subject.",
        "role": "The row the knowledge map reads, and what a subject's percent completion is counted from: passed topics over the topics the syllabus makes assessable.",
        "context": "Marks are normally entered through the grid on a student subject row — one line per topic — rather than added here one at a time. A topic taken again in a later class is a separate result, so the earlier one stays as it was recorded.",
        "fields": [
            ("student_subject", "Which student, which subject, which year — all three in one reference."),
            ("topic", "The topic marked. It has to belong to the subject; anything else is refused."),
            ("score_pct", "The mark out of a hundred. Empty means not assessed yet, which is not the same as failed."),
            ("assessed_on", "The date the mark was given. Set for you when a mark is entered in the grid."),
            ("method", "Where the mark came from: a teacher, a rule, or the AI marker."),
            ("note", "Anything the marker wants on the record — what was weak, what to re-teach."),
        ],
    },
    "teachingassignment": {
        "summary": "Which teacher teaches which syllabus.",
        "role": "The staffing record; the syllabus already implies the class and year.",
        "context": "A teacher and syllabus can appear twice with different roles — a main teacher and a support teacher on the same class.",
        "fields": [
            ("syllabus", "The subject, class and year in one reference."),
            ("role", "primary, support, cover. Part of the uniqueness rule, so both can exist."),
        ],
    },

    # -- question bank -------------------------------------------------
    "question": {
        "summary": "One question in the bank, reusable across papers.",
        "role": "Written against a topic, placed on papers by paper items. Its type decides how it is marked.",
        "context": "Never duplicate a question to reuse it — put the same one on another paper. For multi-part questions, give each part the same group and an order in group; the parts stay independently reusable.",
        "fields": [
            ("question_type", "binary, numeric or text. Decides how it is marked: rule, tolerance, or AI against a prompt."),
            ("question_text", "The question as the student sees it."),
            ("group", "Ties the parts of a multi-part question together, e.g. Q4. Empty for a standalone question."),
            ("order_in_group", "1 for (a), 2 for (b). Required whenever a group is set, and vice versa."),
            ("group_stem", "The shared preamble the parts hang off — the passage, the diagram, the data."),
            ("default_mark", "What it is normally worth. A paper can override it per placement."),
            ("penalty", "Fraction deducted per wrong attempt where a paper allows retries. 0 means none."),
            ("model_answer", "The correct answer in full. AI marking reads this, which is why a shared prompt can stay generic."),
            ("mark_scheme", "How marks are allocated. Also read at marking time."),
            ("default_prompt_version", "Which prompt marks it. Required for text questions, and pinned onto the paper when it locks."),
            ("difficulty", "1 to 5, for building balanced papers. Optional."),
        ],
    },
    "questionattributetype": {
        "summary": "One typed property a question of some type can carry — the answer-key fields, and anything added later.",
        "role": "Replaces per-type tables like the old BinaryConfig/NumericConfig: a question_type's fields (expected_value, tolerance, true_label...) are rows here, filtered by applies_to, so a new field is a new row rather than a new table.",
        "context": "Adding a school-specific field to a question no longer needs a migration — add an attribute type here, then set it per question on the question's own change form.",
        "fields": [
            ("short_name", "The stable key code and imports look this up by. Set once — changing it orphans values stored under the old key."),
            ("datatype", "How the stored text is interpreted: text, yes/no, whole number, decimal, date or date+time."),
            ("datatype_config", "Datatype-specific configuration. For text, a '|'-separated list of allowed values acts as a closed choice set."),
            ("applies_to", "Which question_type this is for. Empty applies to any type."),
            ("min_occurs", "0 means optional. Not enforced by a database constraint."),
            ("max_occurs", "1 means single-valued, the normal case."),
            ("visible", "Hides the type from pickers without deleting it."),
        ],
    },
    "questionattribute": {
        "summary": "One question's value for one QuestionAttributeType.",
        "role": "The answer-key data itself — what used to live in BinaryConfig/NumericConfig rows.",
        "context": "The value is always stored as text (value_reference) and resolved to a real Python value through its attribute type's datatype.",
        "fields": [
            ("question", "The question this value belongs to."),
            ("attribute_type", "Which property this is — and therefore how value_reference is interpreted."),
            ("value_reference", "The value, as text. Read it through get_value() rather than directly."),
        ],
    },
    "evaluationprompt": {
        "summary": "A reusable AI marking instruction.",
        "role": "A library entry many questions point at, rather than a prompt per question.",
        "context": "Written generically — 'a three-mark explanation, Cambridge style' — and it reads the question's own model answer and mark scheme at marking time. That is what makes one prompt safe to share across a hundred questions.",
        "fields": [
            ("name", "How it is picked from the library. Unique, so make it descriptive of the marking style."),
            ("applies_to", "The question type it suits. Almost always text."),
            ("subject", "Restricts it to one subject. Leave empty for a prompt any subject can use."),
            ("owner", "Who maintains it."),
            ("visible", "Hides a prompt from the picker without retiring its versions."),
        ],
    },
    "promptversion": {
        "summary": "The actual text of a prompt, versioned.",
        "role": "What an AI evaluation was carried out with. Papers pin a specific version.",
        "context": "Once active, the text is frozen. Rewording it creates version 2 and leaves version 1 exactly as it marked last year's scripts.",
        "fields": [
            ("version_no", "1, 2, 3. Unique within the prompt, and what a locked paper pins."),
            ("prompt_text", "The instruction sent to the model. Read-only once active."),
            ("rubric_json", "Structured mark allocation, where the marking needs more than prose."),
            ("required_variables", "Question fields this prompt expects, e.g. mark_scheme. Checked when a paper locks, so a prompt is never attached to a question that cannot feed it."),
            ("status", "draft while being written, active once in use, retired when superseded."),
            ("effective_from", "The date it takes over. For the record; pinning is what actually decides."),
        ],
    },

    # -- papers --------------------------------------------------------
    "questionpaper": {
        "summary": "A paper's stable identity — 'S2 Physics, Mid-Term'.",
        "role": "Holds no questions itself; its versions do.",
        "context": "The name stays the same year after year. What changes is which version is current.",
        "fields": [
            ("purpose", "quiz, assignment, exam or mock. Affects how it is presented and reported."),
            ("subject", "and class — who the paper is for."),
            ("intro", "Front-page instructions shown before the first question."),
            ("owner", "Who is responsible for it."),
        ],
    },
    "paperversion": {
        "summary": "A frozen set of questions: one version of a paper.",
        "role": "Editable while draft. Locking freezes it and pins each text question's prompt version.",
        "context": "A locked paper is never edited — clone it, and the clone becomes the next version. That is what lets you re-open last year's paper and see exactly what students sat.",
        "fields": [
            ("version_no", "1, 2, 3 within the paper. A clone takes the next number."),
            ("status", "draft is editable; locked is frozen and issuable; retired is out of use."),
            ("date_locked", "When it was frozen, and locked_by is who did it. Both required once locked."),
            ("cloned_from_version", "The version this one was copied from — the chain back to v1."),
            ("total_marks", "Summed from the items when it locks. Not typed in."),
            ("duration_minutes", "How long the paper is meant to take. The enforced limit lives on the assignment."),
        ],
    },
    "paperitem": {
        "summary": "One question in one slot of one paper version.",
        "role": "Carries the marks for that question on that paper, and the prompt version it will be marked by.",
        "context": "The same question can be slot 3 on one paper and slot 11 on another, worth different marks. Once the version is locked, none of it can change.",
        "fields": [
            ("slot", "Position on the paper. Unique within the version — no two questions share a slot."),
            ("page", "Which page it appears on, for paginated delivery."),
            ("max_mark", "What it is worth here. Overrides the question's default mark."),
            ("require_previous", "Blocks this question until the previous one is answered."),
            ("prompt_version", "The exact prompt this item is marked by, pinned when the paper locks."),
            ("section_label", "Section A, Section B — for printed papers and grouping."),
        ],
    },
    "paperassignment": {
        "summary": "Issues a locked paper version to a class or a cohort.",
        "role": "Sets the window, the time limit, how many attempts are allowed and which one counts.",
        "context": "Leave the cohort empty to issue to the whole class; set it to give one group a different paper or a resit.",
        "fields": [
            ("student_cohort", "Narrows the audience to one group within the class. Empty means everyone."),
            ("time_open", "When students may start; time_close is the deadline."),
            ("time_limit", "Seconds allowed once started. Empty means untimed."),
            ("attempts", "How many sittings are allowed. 0 means unlimited."),
            ("marking_method", "Which sitting counts: highest, average, first or last."),
            ("preferred_behaviour", "When feedback appears — deferred until marking, or immediately."),
            ("shuffle_questions", "Randomises slot order per student."),
            ("is_practice", "Marks it as practice, so results are not treated as a record."),
        ],
    },
    "studentcohort": {
        "summary": "A group of students inside one class.",
        "role": "Any grouping — a quiz team, a reading circle, a remedial set. Papers can be assigned to one.",
        "context": "Always inside a single class; cohorts never span classes.",
        "fields": [
            ("purpose", "activity, interest, remedial or other. What the group is for."),
            ("academy_class", "and academic_year — the class and year it sits inside. Required."),
            ("is_temporary", "A group for one activity rather than the whole year."),
            ("starts_on", "and ends_on — the period it exists for. Optional."),
        ],
    },
    "cohortmembership": {
        "summary": "A student's membership of a cohort, through their enrolment.",
        "role": "The link between a cohort and the students in it.",
        "context": "Going through the enrolment rather than the student is what guarantees a member is actually in that class this year.",
        "fields": [
            ("enrolment", "The student's placement for the year, not the student directly."),
            ("student_cohort", "The group they belong to. One live row per pairing."),
        ],
    },

    # -- marking -------------------------------------------------------
    "attempt": {
        "summary": "One student's sitting of one assignment.",
        "role": "Holds the answers and the total. Repeat sittings are separate attempts.",
        "context": "Only one attempt counts toward the record; which one follows the assignment's marking method. Preview attempts by staff never count.",
        "fields": [
            ("attempt_no", "1 for the first sitting, 2 for a resit. Unique per student per assignment."),
            ("is_counted", "Marks the attempt that feeds the record. Recomputed from the assignment's marking method; exactly one per student can carry it."),
            ("preview", "A staff run-through. Never counts and never appears in results."),
            ("state", "in_progress, overdue, finished or abandoned."),
            ("time_start", "and time_finish — when the sitting began and ended."),
            ("total_marks", "Summed from the evaluations once marking is done."),
        ],
    },
    "answer": {
        "summary": "A student's response to one item of a paper.",
        "role": "Stored in the column matching the question's type, then evaluated.",
        "context": "One answer per item per attempt. Files a student submits attach here.",
        "fields": [
            ("boolean_response", "Filled for binary questions; the other response columns stay empty."),
            ("numeric_response", "Filled for numeric questions, compared against the tolerance."),
            ("text_response", "Filled for text questions, and what the AI marks."),
            ("response_summary", "A rendered version for reports and review screens."),
            ("date_answered", "When it was submitted, which may be before the attempt finished."),
        ],
    },
    "evaluation": {
        "summary": "A marking event on one answer.",
        "role": "Rule-marked, AI-marked, or a teacher's decision.",
        "context": "Append-only. A teacher who disagrees with the AI adds a new evaluation pointing at the one it supersedes — the original score, confidence and feedback are kept, which is what makes the AI's marking reviewable.",
        "fields": [
            ("method", "rule for binary and numeric, ai for prompt-marked text, teacher for a human decision."),
            ("awarded_marks", "The marks given, in the paper's units."),
            ("fraction", "The same as a proportion, 0 to 1 — what the mark scheme awarded."),
            ("confidence", "How sure the model was, 0 to 1. Low confidence is the queue for human review."),
            ("prompt_version", "The exact prompt used. Required for AI marking."),
            ("supersedes", "The evaluation this one replaces. Set on a teacher override; the original stays."),
            ("evaluated_by", "The teacher who marked or overrode. Required for a teacher decision."),
        ],
    },

    # -- handouts and hand-ins -----------------------------------------
    "handout": {
        "summary": "A sheet given out in class, and the work handed back from it.",
        "role": "The light route beside the exam machinery. Everything a student hands in points at one of these, and its marks reach the subject average through the topic it belongs to.",
        "context": "A teacher writing tonight's homework attaches a sheet and hands it out. Building a versioned question paper for that would be wrong, and the paper route is still there for a real exam. Printed copies are identical: nothing on the page says whose it is, because the submission carries that.",
        "fields": [
            ("syllabus", "The subject, class and year it belongs to. A handout hangs off the syllabus, not a single lesson, so one sheet can cover a week."),
            ("code", "Set on first save: SUBJECT-CLASS-YEAR-Hnnn. Printed on the sheet and quoted by every submission."),
            ("topic", "The catalogued topic, so it appears beside that topic on the teacher's day. Optional — chapter and topic (as written) are what a teacher usually types."),
            ("is_assignment", "Students hand work back. Clear it for a sheet that is only to read."),
            ("kind", "Assignment is set in class. The exam kinds are sat under supervision, are never shown to a class in advance, and aggregate separately from coursework."),
            ("weight_override", "Empty means inherit the topic's importance, which is the normal case. Set it only for a paper that should count more or less than its topic."),
            ("counts_toward_grade", "Clear it for practice work that is marked but should not move the average."),
            ("open_from", "Students see it from this moment, and not before. Empty means as soon as it is handed out."),
            ("due_date", "When the work is expected. Not the same as when the door shuts."),
            ("allow_late", "Keep taking work after the due date, marked late. Off means the due date is the close."),
            ("cutoff_at", "When the door actually shuts, used only when late work is allowed. Empty then means late work is taken indefinitely; equal to the due date is a hard stop."),
            ("max_rounds", "Hand-ins allowed, counting the first. Three means one attempt and two redoes."),
            ("status", "Draft while it is being written, Active once handed out — which is also when the class can see it — then Closed."),
            ("date_activated", "When it was handed out. Stamped by activating, not typed."),
        ],
    },
    "handoutlesson": {
        "summary": "Which lessons a handout belongs to.",
        "role": "The link between a sheet and the classes it covers, so both the lesson and the handout can list the other.",
        "context": "Usually one. A sheet covering a week of classes lists several, and a lesson carrying both classwork and homework appears in two handouts.",
        "fields": [
            ("handout", "The sheet."),
            ("lesson", "The class it belongs to. One pair only — the same lesson cannot be listed twice on the same handout."),
            ("sort_order", "The order the lessons read in, when a sheet spans several."),
        ],
    },
    "handoutsheet": {
        "summary": "One version of the sheet students were given.",
        "role": "What a submission actually answered. Every hand-in records the version number it was working from.",
        "context": "A teacher finds a typo at eight in the evening, after half the class has handed in. Deleting and re-posting strands everyone who already submitted; editing in place makes a mark refer to a sheet that no longer exists. So a replacement becomes version 2 and the earlier one stays exactly as it was issued.",
        "fields": [
            ("version_no", "1 upward, within the handout. A submission's sheet version points here."),
            ("attachment", "The file itself, stored with everything else."),
            ("note", "What changed, for whoever reads this later."),
            ("replaced_on", "When a later version took over. Empty on the current one."),
        ],
    },
    "handoutextension": {
        "summary": "A later deadline for one student on one handout.",
        "role": "Read wherever the deadline is: it moves the close for this student and nobody else.",
        "context": "Not a second handout. The same sheet, the same code, the same marks column — only the date moves. Issuing a fresh handout instead would double-count the work and split the record in two.",
        "fields": [
            ("handout", "The sheet whose deadline moves."),
            ("enrolment", "Whose deadline it is. One extension per student per handout."),
            ("extended_to", "Their new deadline."),
            ("reason", "Why it was given. Worth writing — it is what an appeal months later is answered from."),
            ("granted_by", "Who gave it."),
        ],
    },
    "submission": {
        "summary": "One student's work handed back for one handout, in one round.",
        "role": "What the examiner checks and the teacher approves. Marks, feedback and the autograding jobs all hang off it.",
        "context": "Nothing is overwritten. A redo is its own row at the next round number, so 'right first time' stays visible. Before an examiner opens it, and while the window is still open, a student may replace their own hand-in — the replaced row is voided rather than deleted and keeps its round number, so the record still shows what arrived first.",
        "fields": [
            ("handout", "The sheet this answers."),
            ("enrolment", "Whose work, and in which class and year — so the record stays true after they move up."),
            ("code", "Stamped with the moment it arrived: handout code, admission number, timestamp. Identifies this hand-in and no other."),
            ("round_no", "1 is the first hand-in; 2 and 3 are redoes of what was marked wrong. Capped by the handout's max rounds."),
            ("state", "Whose desk it is on. Waiting for the examiner, being marked, checked and waiting for teacher approval, sent back to the examiner, approved and released, or returned to the student to redo. Being marked also means the student can no longer replace the file."),
            ("awarded_marks", "This round's marks. The running total across rounds is worked out, not stored."),
            ("sheet_version", "Which version of the sheet this answered. 0 for work handed in before sheets were versioned."),
            ("is_late", "Handed in after the due moment. Late is recorded, not refused — the cut-off is what refuses."),
            ("minutes_late", "How late, in minutes. Kept because 'ten minutes' and 'three days' are not the same conversation."),
            ("marked_by", "The examiner who checked it."),
            ("approved_by", "The teacher who released it to the student. Until this is set, the student sees nothing."),
            ("sent_back_reason", "Why the teacher returned it to the examiner to re-check."),
            ("redo_reason", "What the student is being asked to put right. A redo happens only when a teacher asks for one; nothing comes back automatically."),
        ],
    },
    "autogradejob": {
        "summary": "One request to have a submission marked by the autograding service.",
        "role": "The seam to a service that lives outside this codebase. It records what was asked, what came back, and how sure the service was.",
        "context": "Nothing here marks anything by itself. The service's marks land as lines attributed to the autograder, sitting in the examiner's queue and released only after a person confirms them — so a wrong answer costs an examiner half a minute and never reaches a child. A failed job is not a blocked submission: the examiner marks by hand exactly as they would have anyway.",
        "fields": [
            ("submission", "The work that was sent. The file goes out under a signed link and no student identity travels with it."),
            ("status", "Queued, Running, Done, Failed or Skipped."),
            ("service_ref", "The service's own id for this run, for tracing a result back to its logs."),
            ("confidence", "How sure the service was, if it says. Low confidence is a reason to look, not a reason to reject."),
            ("raw_response", "Exactly what came back, kept verbatim so a disputed mark can be checked against the source rather than the summary."),
            ("error", "Why it failed, if it did."),
            ("completed_at", "When the result or the failure arrived. Empty while it is still out."),
        ],
    },

    # -- the notice board ----------------------------------------------
    "notice": {
        "summary": "Something the school puts in front of a class: an exam timetable, an exam syllabus, or a plain notice.",
        "role": "What students see on their notice board, decided from the clock rather than a flag.",
        "context": "Deliberately a file rather than structured rows. A quarterly timetable is produced once a term as a document, and re-typing it into the system would be work with no reader — nobody queries an exam timetable, they look at it.",
        "fields": [
            ("category", "Exam timetable, exam syllabus or a general notice. It is what the board groups by."),
            ("academy_class", "Which class it is for. Empty means every class sees it."),
            ("academic_year", "The year it belongs to, so old timetables fall off the board."),
            ("body", "A line or two of context. The file is the notice; this is optional."),
            ("published_from", "Students see it from this moment. Empty means immediately."),
            ("published_until", "It drops off the board after this. Empty means it stays."),
            ("date_posted", "When it went up. What the board sorts by."),
        ],
    },

    # -- attendance ----------------------------------------------------
    "attendancesession": {
        "summary": "One register: a class, a date, a period.",
        "role": "The header a set of attendance marks belongs to.",
        "context": "Leave the syllabus empty for a whole-day register; set it to take attendance for one lesson. Both can exist for the same day.",
        "fields": [
            ("date", "The day being registered."),
            ("period", "full_day for the daily register, or a period label such as 1 or assembly."),
            ("syllabus", "Set for a lesson register, empty for a day register. Class, year, date, period and this together are unique."),
            ("taken_by", "Who called the register."),
            ("is_finalised", "Marks the register as settled, so later edits are deliberate."),
        ],
    },
    "attendancerecord": {
        "summary": "One student's mark in one register.",
        "role": "Present, absent, late, excused or on approved leave.",
        "context": "Marking a register defaults everyone to present, so only the exceptions are entered. Correcting a mark updates it; the audit block records who changed it and when.",
        "fields": [
            ("status", "present, absent, late, excused (absence with a reason accepted) or leave (approved in advance)."),
            ("enrolment", "The student, through their placement for the year."),
            ("minutes_late", "How late, where it matters. Only meaningful with status late."),
            ("note", "A short reason. The detail behind an excused absence."),
        ],
    },

    # -- files ---------------------------------------------------------
    "attachment": {
        "summary": "A stored file: image, PDF, audio, video or anything else.",
        "role": "Lives under the media root in a flat folder for its kind.",
        "context": "Use the Upload files button for anything large — it sends the file in pieces and can resume. Uploading a file that is already stored reuses the existing record instead of keeping two copies.",
        "fields": [
            ("kind", "picture, video, audio, text or other. Decided from the MIME type, falling back to the extension, and it decides which folder the file lands in."),
            ("original_filename", "The name it was uploaded under. On disk it is stored as its uuid, so nothing collides."),
            ("checksum", "SHA-256 of the contents. Unique among live rows — this is what makes re-uploading the same file reuse the record."),
            ("size_bytes", "Size on disk."),
            ("title", "and caption — what people see instead of the filename."),
            ("width", "height and duration_seconds — filled in for pictures and media where known."),
        ],
    },
    "attachmentlink": {
        "summary": "Attaches a file to a row — a question, an answer, a topic, a paper.",
        "role": "One file can be linked in several places without being stored twice.",
        "context": "This is why no model has its own file columns: anything can carry attachments.",
        "fields": [
            ("attachment", "The stored file."),
            ("content_type", "and object_id — which row it is attached to."),
            ("role", "What the file is for there: figure, diagram, mark_scheme, submission, resource."),
            ("sort_order", "Order when a row carries several files."),
        ],
    },
    "uploadsession": {
        "summary": "A large upload in progress.",
        "role": "Tracks how many bytes have arrived so an interrupted upload can resume.",
        "context": "Housekeeping. Completed sessions point at the attachment they produced; open ones left over from a cancelled upload can be voided.",
        "fields": [
            ("received", "Bytes stored so far. The browser resumes from this number."),
            ("declared_size", "What the browser said the file would be."),
            ("state", "open while receiving, completed once assembled, aborted if cancelled."),
            ("attachment", "The file it produced. Empty until it completes."),
        ],
    },

    # -- retention -----------------------------------------------------
    "retentionpolicy": {
        "summary": "How long voided rows of a table are kept before they may be purged.",
        "role": "Purging only touches tables enabled here.",
        "context": "Left disabled for attempts, answers and evaluations — assessment evidence is not destroyed on a timer.",
        "fields": [
            ("target_table", "The table this policy governs. One row per table."),
            ("void_retention_days", "How long a voided row must sit before it may be purged."),
            ("purge_enabled", "Off means rows in this table are never destroyed, however old."),
        ],
    },
    "purgerun": {
        "summary": "A record of rows permanently destroyed.",
        "role": "The audit trail for purging, and the one table that is never purged itself.",
        "context": "Read-only. If something is missing and was not voided, this is where to look.",
        "fields": [
            ("target_table", "Which table was purged."),
            ("criteria", "The predicate that selected the rows."),
            ("row_ids", "Exactly which rows were destroyed."),
            ("ran_by", "Who ran it, and date_run when."),
        ],
    },
}


def help_for(model):
    """The help entry for a model, or None if it has none."""
    return ENTITY_HELP.get(model._meta.model_name)
