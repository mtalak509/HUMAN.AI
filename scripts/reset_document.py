"""
Сброс одного документа для повторной ингестии.

Запуск:
    python scripts/reset_document.py <document_id>
    python scripts/reset_document.py            # дефолт: резюме Талакина

Зачем: writer пишет идемпотентно по детерминированным id. Если граф кандидата
уже записан с ошибкой (например, до фикса education-id схлопнулись три диплома
из одного вуза в одну ноду Education), простая перезагрузка PDF не поможет —
status-smart dedup (D-05) увидит статус `written` и вернёт 200 без перезапуска.

Что делает скрипт:
  1. DETACH DELETE подграфа кандидата — только СОБСТВЕННЫЕ ноды
     (Candidate + Contact/Experience/Education, чьи id детерминированы от
     document_id). Общие Skill/Company/Institution НЕ удаляются — они
     принадлежат многим кандидатам; DETACH лишь отвязывает рёбра.
  2. Переводит Document в статус `failed` (failed_stage="write"), чтобы
     последующий `POST /documents` пошёл по ветке reset_for_requeue +
     re-enqueue (D-05/D-06) и прогнал пайплайн заново.

После запуска: повторно загрузите тот же PDF через `POST /documents` —
пайплайн перезапишет граф начисто (с фиксом теперь три диплома → три ноды).

Идемпотентно и безопасно для повторного запуска (MATCH ничего не находит — no-op).
"""

import asyncio
import sys

from loguru import logger

from core.config import get_settings
from core.graph import GraphDB
from core.pipeline.status import set_failed

# Резюме Талакина (кейс, ради которого писался скрипт) — дефолт для удобства.
DEFAULT_DOCUMENT_ID = (
    "eeccdb91c062e0affb488c3fc9a25f40fb8006586d70c61b31bb825ca8c3051c"
)

# Удаляем кандидата и его СОБСТВЕННЫЕ ноды одним атомарным запросом.
# Собираем именно ноды ЭТОГО кандидата (привязаны рёбрами HAS_*), считаем их
# size() ДО удаления, затем DETACH DELETE каждой через FOREACH + самого
# кандидата. Skill/Company/Institution — общие, под match не попадают; DETACH
# лишь снимает рёбра к ним. Ни одна чужая нода не затрагивается.
_DELETE_CANDIDATE_SUBTREE = """
MATCH (c:Candidate {id: $document_id})
OPTIONAL MATCH (c)-[:HAS_CONTACT]->(ct:Contact)
OPTIONAL MATCH (c)-[:HAS_EXPERIENCE]->(e:Experience)
OPTIONAL MATCH (c)-[:HAS_EDUCATION]->(ed:Education)
WITH c,
     collect(DISTINCT ct) AS cts,
     collect(DISTINCT e)  AS exps,
     collect(DISTINCT ed) AS edus
WITH c, cts, exps, edus,
     size(cts) AS contacts, size(exps) AS experiences, size(edus) AS educations
FOREACH (x IN cts  | DETACH DELETE x)
FOREACH (x IN exps | DETACH DELETE x)
FOREACH (x IN edus | DETACH DELETE x)
DETACH DELETE c
RETURN contacts, experiences, educations
"""


async def _reset(session, document_id: str) -> None:  # noqa: ANN001
    # 1. Снести подграф кандидата (если он есть).
    result = await session.run(_DELETE_CANDIDATE_SUBTREE, document_id=document_id)
    record = await result.single()
    if record is None:
        logger.warning(
            "Candidate id={} не найден — подграф удалять нечего", document_id
        )
    else:
        logger.info(
            "deleted candidate subtree: contacts={} experiences={} educations={}",
            record["contacts"],
            record["experiences"],
            record["educations"],
        )

    # 2. Перевести Document в failed → повторный POST переочередит обработку.
    await set_failed(
        session,
        document_id=document_id,
        error="manual reset for re-ingestion (education-id fix)",
        failed_stage="write",
    )
    logger.info("Document id={} → status=failed (готов к re-POST)", document_id)


async def main() -> None:
    document_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DOCUMENT_ID

    settings = get_settings()
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    try:
        await db.connect_with_retry()
        if not db.is_connected:
            logger.error("Neo4j unavailable — reset aborted")
            sys.exit(1)
        async with db.session() as session:
            await _reset(session, document_id)
        logger.info(
            "Reset complete. Теперь повторно загрузите PDF: "
            "POST /documents (тот же файл) — пайплайн перезапишет граф."
        )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
