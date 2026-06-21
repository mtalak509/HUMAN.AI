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
    Candidate   → id   (candidate_id_unique)
    Contact     → id   (contact_id_unique)
    Skill       → name (skill_name_unique)
    Company     → name (company_name_unique)
    Experience  → id   (experience_id_unique)
    Education   → id   (education_id_unique)
    Institution → name (institution_name_unique)

Refactor (2026-06-21): the Fact provenance layer and the Role node were removed.
    - Fact was pure overhead in the 1:1 (one resume = one candidate = one document)
      reality — it carried no information not already on the target node or the
      single Document. Provenance now lives on the Candidate-[:SOURCED_FROM]->Document
      edge (model_version + extracted_at as edge properties). The Fact layer returns
      with entity resolution (v1.2), when one candidate spans multiple documents.
    - Role became Experience.role (a free-form title is noise as a shared node).
    - Education's institution became a shared Institution node (mirrors Company),
      so "find graduates of X" becomes a graph traversal.
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
# role + description are stored on the node (role is no longer a shared Role node;
# description is the semantic-search payload — see project_status §3).
# MERGE on .id only (experience_id_unique constraint — do not change the key).
MERGE_EXPERIENCE = """
MERGE (n:Experience {id: $id})
SET n.role = $role, n.description = $description,
    n.from_date = $from_date, n.to_date = $to_date, n.is_current = $is_current
"""

# institution moved to a shared Institution node (AT_INSTITUTION edge) — the
# Education node now carries only the enrollment-specific facets.
# MERGE on .id only (education_id_unique constraint — do not change the key).
MERGE_EDUCATION = """
MERGE (n:Education {id: $id})
SET n.degree = $degree, n.field = $field,
    n.from_date = $from_date, n.to_date = $to_date
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

# institution_name_unique constraint — MERGE key is name, do not add a synthetic id.
# Mirrors Company: schools are first-class shared entities ("find graduates of X").
MERGE_INSTITUTION = "MERGE (n:Institution {name: $name})"

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

LINK_HAS_EDUCATION = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (ed:Education {id: $ed_id}) "
    "MERGE (c)-[:HAS_EDUCATION]->(ed)"
)

# Education→Institution — mirrors LINK_AT_COMPANY (Experience→Company).
LINK_AT_INSTITUTION = (
    "MATCH (ed:Education {id: $ed_id}) MATCH (i:Institution {name: $name}) "
    "MERGE (ed)-[:AT_INSTITUTION]->(i)"
)

# D-06: Experience→Skill for skills_mentioned in a specific role.
# Structurally mirrors LINK_HAS_SKILL but sourced from Experience rather than Candidate.
# No uniqueness constraint needed on edges (edges have no uniqueness keys).
LINK_USED_SKILL = (
    "MATCH (e:Experience {id: $e_id}) MATCH (s:Skill {name: $name}) "
    "MERGE (e)-[:USED_SKILL]->(s)"
)

# ---------------------------------------------------------------------------
# Provenance backbone — Candidate-[:SOURCED_FROM]->Document
# Replaces the reified Fact layer in the 1:1 world. Extraction metadata
# (model_version, extracted_at) lives on the edge: it describes the extraction
# EVENT, not the person. T-06-02: MATCH (never MERGE) Document — the parser
# (phase 4) is the sole creator of the Document node.
# ---------------------------------------------------------------------------

LINK_SOURCED_FROM = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (d:Document {id: $d_id}) "
    "MERGE (c)-[r:SOURCED_FROM]->(d) "
    "SET r.model_version = $model_version, r.extracted_at = $extracted_at"
)
