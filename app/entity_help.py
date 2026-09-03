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
            ("groups", "Their roles. Admin, Teaching Staff, Non-academic Staff, Student, Guardian or Guest — this is what decides what they can reach."),
            ("is_staff", "May open the admin at all. A student or guardian account should not have it."),
            ("is_active", "Django's login switch. Turning it off blocks sign-in immediately."),
            ("suspended", "The school's own state, separate from is_active: on the roll but stood down."),
            ("id_number", "External identifier for imports and reports. Optional, unique when present."),
        ],
    },
    "grade": {
        "summary": "A grade, which here is also the class.",
        "role": "Students enrol into a grade for a year; syllabi, cohorts, papers and registers all hang off it.",
        "context": "E1 and E2 are Lower Secondary (Cambridge stages 7–8). S1, S2 and S3 run the O Level programme. S3 is the terminal grade — the only one where students take different subjects.",
        "fields": [
            ("level", "The Cambridge stage number: 7 and 8 for E1/E2, 9 to 11 for S1–S3. Unique, and what the grades sort by."),
            ("short_name", "E1, S3 — what staff type and what appears in lists."),
            ("is_terminal", "Marks the final grade, where subjects differ per student. Only S3 has it."),
            ("capacity", "Places in the class. Optional, and not enforced — it is there for planning."),
            ("visible", "Hides the grade from pickers without deleting it. Not the same as voiding."),
        ],
    },
    "student": {
        "summary": "A student, independent of the grade they currently sit in.",
        "role": "The person record. Their placement each year is an Enrolment, so history survives when they move up.",
        "context": "Admission number is the identifier staff actually use. Guardian name and contact are the details on the record; a guardian's *access* is a separate Guardian link.",
        "fields": [
            ("admission_no", "The school's identifier. Unique among live records, and the field to search by."),
            ("user", "Their login, if they have one. Empty for students who never sit papers online."),
            ("guardian_name", "Contact detail only. It grants nobody any access."),
            ("guardian_contact", "The number the office rings. Also just a detail."),
            ("date_of_birth", "Used for reports and age checks; optional."),
            ("photo", "Their portrait. Square — the width must equal the height — and under 100 KB. Stored with the other pictures and shown as the avatar in lists."),
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
        "summary": "Places one student in one grade for one academic year.",
        "role": "The row nearly everything year-scoped hangs off: subject choices, cohort membership, attendance.",
        "context": "A student can hold only one live enrolment per year. If one is wrong, void it and create the correction — the voided row keeps the audit trail and does not block the new one.",
        "fields": [
            ("academic_year", "A plain year number, 2026. Together with the student it is the uniqueness rule."),
            ("grade", "Which class they are in that year. Change of grade mid-year means voiding this and creating another."),
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
        "role": "Owns its topics; a syllabus offers it to a grade in a year.",
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
        "summary": "One subject, taught to one grade, in one academic year.",
        "role": "Both the offering and the topic list for that run. Teaching assignments and student subject choices point here.",
        "context": "This is where a year's curriculum actually differs from the last. Core subjects are taken by everyone in the grade; in S3 the non-core ones are chosen.",
        "fields": [
            ("subject", "What is taught."),
            ("grade", "Who it is taught to."),
            ("academic_year", "When. Subject, grade and year together are unique — one syllabus per run."),
            ("is_core", "Everyone in the grade takes it. Clear it for an S3 elective, which students then choose."),
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
        "context": "Marks are normally entered through the grid on a student subject row — one line per topic — rather than added here one at a time. A topic taken again in a later grade is a separate result, so the earlier one stays as it was recorded.",
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
        "role": "The staffing record; the syllabus already implies the grade and year.",
        "context": "A teacher and syllabus can appear twice with different roles — a main teacher and a support teacher on the same class.",
        "fields": [
            ("syllabus", "The subject, grade and year in one reference."),
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
    "binaryconfig": {
        "summary": "The answer key for a true/false question.",
        "role": "Marked by rule, with no partial credit.",
        "context": "All or nothing, by design. If a question deserves partial marks, it is not a binary question.",
        "fields": [
            ("expected_value", "The correct answer. Ticked means true."),
            ("true_label", "What the student sees instead of 'True' — Yes, Agree, Valid."),
            ("false_label", "The same for the other option."),
            ("true_feedback", "Shown when they answer true. Useful for explaining a common mistake."),
        ],
    },
    "numericconfig": {
        "summary": "The expected value and tolerance for a numeric question.",
        "role": "Marked by rule: within tolerance is correct.",
        "context": "Tolerance is what makes this usable in physics and maths. The partial band optionally awards part marks to answers just outside it.",
        "fields": [
            ("expected_value", "The correct number."),
            ("tolerance_type", "absolute is ± a fixed amount; relative is ± a percentage; geometric scales with magnitude."),
            ("tolerance", "The size of that band. 0 demands the exact value."),
            ("partial_band", "A wider band outside tolerance that still earns something."),
            ("partial_fraction", "What that wider band earns, as a fraction of the mark — 0.5 for half."),
            ("unit", "The expected unit, where one is required."),
            ("unit_penalty", "Fraction lost for the right number with the wrong unit."),
            ("significant_figures", "Figures the answer is expected to. Optional."),
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
            ("subject", "and grade — who the paper is for."),
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
        "summary": "Issues a locked paper version to a grade or a cohort.",
        "role": "Sets the window, the time limit, how many attempts are allowed and which one counts.",
        "context": "Leave the cohort empty to issue to the whole grade; set it to give one group a different paper or a resit.",
        "fields": [
            ("student_cohort", "Narrows the audience to one group within the grade. Empty means everyone."),
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
        "summary": "A group of students inside one grade.",
        "role": "Any grouping — a quiz team, a reading circle, a remedial set. Papers can be assigned to one.",
        "context": "Always inside a single grade; cohorts never span grades.",
        "fields": [
            ("purpose", "activity, interest, remedial or other. What the group is for."),
            ("grade", "and academic_year — the class and year it sits inside. Required."),
            ("is_temporary", "A group for one activity rather than the whole year."),
            ("starts_on", "and ends_on — the period it exists for. Optional."),
        ],
    },
    "cohortmembership": {
        "summary": "A student's membership of a cohort, through their enrolment.",
        "role": "The link between a cohort and the students in it.",
        "context": "Going through the enrolment rather than the student is what guarantees a member is actually in that grade this year.",
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

    # -- attendance ----------------------------------------------------
    "attendancesession": {
        "summary": "One register: a grade, a date, a period.",
        "role": "The header a set of attendance marks belongs to.",
        "context": "Leave the syllabus empty for a whole-day register; set it to take attendance for one lesson. Both can exist for the same day.",
        "fields": [
            ("date", "The day being registered."),
            ("period", "full_day for the daily register, or a period label such as 1 or assembly."),
            ("syllabus", "Set for a lesson register, empty for a day register. Grade, year, date, period and this together are unique."),
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
