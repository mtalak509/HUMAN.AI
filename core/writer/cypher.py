"""Parameterized Cypher statement library for the Graph Writer.

All constants are plain string templates with ``$param`` placeholders.
Resume-derived values NEVER enter query text via string interpolation —
this module is the Cypher-injection trust boundary (T-06-01).

Idempotency policy (WRITE-04 / D-08):
    Every node MERGE uses plain ``SET`` (never the conditional ON-CREATE/ON-MATCH
    form from scripts/seed.py).  A repeated write() of the same document REFRESHES
    the node in-place without creating duplicates.  Canonical template:
    core/parser/pdf.py ``MERGE_DOCUMENT_CYPHER``.

MERGE-key source of truth: core/database/migrations.py CONSTRAINTS.
    Candidate  → id   (candidate_id_unique)
    Contact    → id   (contact_id_unique)
    Skill      → name (skill_name_unique)
    Role       → title (role_title_unique)
    Company    → name (company_name_unique)
    Experience → id   (experience_id_unique)
    Education  → id   (education_id_unique)
    Fact       → id   (fact_id_unique)
"""

# ---------------------------------------------------------------------------
# Node MERGEs — id-keyed
# ---------------------------------------------------------------------------

# MERGE on .id only (candidate_id_unique constraint — do not change the key).
# Candidate.full_name is index-backed (candidate_full_name_idx) — always set it.
MERGE_CANDIDATE = """
MERGE (n:Candidate {id: $id})
SET n.full_name = $full_name, n.status = $status
RETURN n
"""

# MERGE on .id only (contact_id_unique constraint — do not change the key).
MERGE_CONTACT = """
MERGE (n:Contact {id: $id})
SET n.type = $type, n.value = $value
"""

# Experience.is_current is index-backed (experience_is_current_idx) — always set it.
# MERGE on .id only (experience_id_unique constraint — do not change the key).
MERGE_EXPERIENCE = """
MERGE (n:Experience {id: $id})
SET n.from_date = $from_date, n.to_date = $to_date, n.is_current = $is_current
"""

# MERGE on .id only (education_id_unique constraint — do not change the key).
MERGE_EDUCATION = """
MERGE (n:Education {id: $id})
SET n.institution = $institution, n.degree = $degree,
    n.field = $field, n.from_date = $from_date, n.to_date = $to_date
"""

# D-02: confidence = null (extractor does not emit confidence — do NOT copy seed's 0.95/1.0).
# predicate + is_current are index-backed (fact_predicate_idx, fact_is_current_idx).
# extracted_at is populated by the writer (not the LLM) to stamp provenance time.
# MERGE on .id only (fact_id_unique constraint — do not change the key).
MERGE_FACT = """
MERGE (n:Fact {id: $id})
SET n.predicate = $predicate, n.value = $value,
    n.confidence = $confidence, n.model_version = $model_version,
    n.is_current = $is_current, n.extracted_at = $extracted_at
"""

# ---------------------------------------------------------------------------
# Node MERGEs — natural-key (no synthetic id, D-01)
# ---------------------------------------------------------------------------

# D-05: Skill carries ONLY name (verbatim, no canonicalization). MERGE key = name.
# skill_name_unique constraint — MERGE key is name, do not add a synthetic id.
MERGE_SKILL = "MERGE (n:Skill {name: $name})"

# company_name_unique constraint — MERGE key is name, do not add a synthetic id.
MERGE_COMPANY = """
MERGE (n:Company {name: $name})
SET n.industry = $industry
"""

# role_title_unique constraint — MERGE key is title, do not add a synthetic id.
MERGE_ROLE = """
MERGE (n:Role {title: $title})
SET n.seniority = $seniority
"""

# ---------------------------------------------------------------------------
# Denormalized edge statements (MATCH→MATCH→MERGE)
# Parameterized — never interpolate resume-derived strings into query text (T-06-01).
# ---------------------------------------------------------------------------

LINK_HAS_CONTACT = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (ct:Contact {id: $ct_id}) "
    "MERGE (c)-[:HAS_CONTACT]->(ct)"
)

LINK_HAS_SKILL = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (s:Skill {name: $name}) "
    "MERGE (c)-[:HAS_SKILL]->(s)"
)

LINK_HAS_EXPERIENCE = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (e:Experience {id: $e_id}) "
    "MERGE (c)-[:HAS_EXPERIENCE]->(e)"
)

LINK_AT_COMPANY = (
    "MATCH (e:Experience {id: $e_id}) MATCH (co:Company {name: $name}) "
    "MERGE (e)-[:AT_COMPANY]->(co)"
)

LINK_AS_ROLE = (
    "MATCH (e:Experience {id: $e_id}) MATCH (r:Role {title: $title}) "
    "MERGE (e)-[:AS_ROLE]->(r)"
)

LINK_HAS_EDUCATION = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (ed:Education {id: $ed_id}) "
    "MERGE (c)-[:HAS_EDUCATION]->(ed)"
)

# D-06: NEW edge type — Experience→Skill for skills_mentioned in a specific role.
# Structurally mirrors LINK_HAS_SKILL but sourced from Experience rather than Candidate.
# No uniqueness constraint needed on edges (edges have no uniqueness keys).
LINK_USED_SKILL = (
    "MATCH (e:Experience {id: $e_id}) MATCH (s:Skill {name: $name}) "
    "MERGE (e)-[:USED_SKILL]->(s)"
)

# ---------------------------------------------------------------------------
# Fact provenance triple (HAS_FACT / EXTRACTED_FROM / SUPPORTS)
# T-06-02: Document is MATCHED by $d_id only — writer never creates/re-creates
# the Document node (owned by core/parser, phase 4).
# ---------------------------------------------------------------------------

LINK_HAS_FACT = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (f:Fact {id: $f_id}) "
    "MERGE (c)-[:HAS_FACT]->(f)"
)

# T-06-02: MATCH (never MERGE) Document — the parser (phase 4) is the sole creator.
LINK_EXTRACTED_FROM = (
    "MATCH (f:Fact {id: $f_id}) MATCH (d:Document {id: $d_id}) "
    "MERGE (f)-[:EXTRACTED_FROM]->(d)"
)

# D-03: SUPPORTS→Skill for has_skill facts.
LINK_SUPPORTS_SKILL = (
    "MATCH (f:Fact {id: $f_id}) MATCH (s:Skill {name: $name}) "
    "MERGE (f)-[:SUPPORTS]->(s)"
)

# D-03: SUPPORTS→Experience for worked_at facts.
LINK_SUPPORTS_EXPERIENCE = (
    "MATCH (f:Fact {id: $f_id}) MATCH (e:Experience {id: $e_id}) "
    "MERGE (f)-[:SUPPORTS]->(e)"
)
