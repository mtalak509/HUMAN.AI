"""
Библиотека параметризованных Cypher-запросов для поиска кандидатов.

Каждая функция принимает AsyncDriver (neo4j), выполняет
параметризованный запрос и возвращает list[dict] результатов.
Модуль не импортирует инфраструктурные обёртки (GraphDB) —
драйвер передаётся вызывающим кодом (тестами, CLI).
"""

from neo4j import AsyncDriver


async def find_candidates_by_skill(driver: AsyncDriver, skill_name: str) -> list[dict]:
    """
    Find candidates who have a specific skill.

    Cypher:
        MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill)
        WHERE toLower(s.name) = toLower($skill_name)
        RETURN c.id AS id, c.full_name AS full_name
    """
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill) "
            "WHERE toLower(s.name) = toLower($skill_name) "
            "RETURN c.id AS id, c.full_name AS full_name",
            skill_name=skill_name,
        )
        return [dict(record) async for record in result]


async def find_candidates_by_company(
    driver: AsyncDriver, company_name: str
) -> list[dict]:
    """
    Find candidates with experience at a specific company.

    Cypher:
        MATCH (c:Candidate)-[:HAS_EXPERIENCE]->(e:Experience)-[:AT_COMPANY]->(co:Company)
        WHERE toLower(co.name) = toLower($company_name)
        RETURN DISTINCT c.id AS id, c.full_name AS full_name
    """
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Candidate)-[:HAS_EXPERIENCE]->(e:Experience)-[:AT_COMPANY]->(co:Company) "
            "WHERE toLower(co.name) = toLower($company_name) "
            "RETURN DISTINCT c.id AS id, c.full_name AS full_name",
            company_name=company_name,
        )
        return [dict(record) async for record in result]


async def find_candidates_by_status(
    driver: AsyncDriver, vacancy_id: str, status: str
) -> list[dict]:
    """
    Find candidates with a specific status in a vacancy pipeline.

    Cypher:
        MATCH (c:Candidate)-[:REACHED_STATUS]->(st:Status)-[:IN_VACANCY]->(v:Vacancy)
        WHERE v.id = $vacancy_id AND st.name = $status
        RETURN c.id AS id, c.full_name AS full_name
    """
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Candidate)-[:REACHED_STATUS]->(st:Status)-[:IN_VACANCY]->(v:Vacancy) "
            "WHERE v.id = $vacancy_id AND st.name = $status "
            "RETURN c.id AS id, c.full_name AS full_name",
            vacancy_id=vacancy_id,
            status=status,
        )
        return [dict(record) async for record in result]


if __name__ == "__main__":
    import asyncio
    from neo4j import AsyncGraphDatabase

    async def main():
        driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "whiterabbit"))
        result_find_candidates_by_skill = await find_candidates_by_skill(driver, "Python")
        print(result_find_candidates_by_skill)
        result_find_candidates_by_company = await find_candidates_by_company(driver, "TechFlow Analytics")
        print(result_find_candidates_by_company)
        result_find_candidates_by_status = await find_candidates_by_status(driver, "v-001", "in_progress")
        print(result_find_candidates_by_status)
        await driver.close()

    asyncio.run(main())
