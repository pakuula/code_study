## Plan: C Analyzer Infrastructure Bootstrap

Цель системы — не восстановить единственную компиляторную модель программы, а построить максимально полный, проверяемый и трассируемый индекс C-кода, пригодный для документирования при отсутствии build-конфигурации.

Подход: эвристический project-agnostic пайплайн на Python 3.13 из ./.venv с проверяемыми стадиями, подробным логированием, CLI+API для каждого шага, и ролями агентов в AGENTS.md. База данных — **верифицируемая индексно-эвристическая БД с трассировкой уверенности и неоднозначностей**, а не точная семантическая модель. sample/seL4 используется только как fixture для тестирования/верификации, без hardcode-зависимостей в скриптах.

**Принципиальные ограничения**
- нет `compile_commands`; сборка недоступна; одна «истинная» конфигурация отсутствует;
- база хранит не только найденные факты, но и степень уверенности (`confidence`), источник факта (`detector`) и причины неоднозначности (`confidence_reason`, `ambiguity_group_id`);
- спорные факты не удаляются — сохраняются как неоднозначные с пометкой источника конфликта.

**Steps**
1. Зафиксировать рамки анализа и контракт данных. Включено: функции, глобальные/локальные переменные, типы struct/union/enum/typedef, макросы #define, includes, reference_candidates, комментарии preceding+inline. Каждая запись несёт: `detector` (tree_sitter/ctags/cscope/regex/manual_rule), `confidence` (HIGH/MEDIUM/LOW), `confidence_reason`, `raw_context`, `ambiguity_group_id`. Ограничения: без compile_commands, без запуска build. *блокирует все последующие шаги*.
2. Спроектировать схему SQLite с индексами под агентные запросы. Помимо основных таблиц добавить: `conditional_regions` (диапазоны #if/#ifdef/#else/#endif), `preprocessor_symbols` (встреченные макросы и условия), `entity_presence_conditions` (при каких #if сущность потенциально существует), `include_resolution_attempts` (все кандидаты include, не только выбранный). *depends on 1*.
3. Сформировать структуру Python-проекта анализатора (модульный пайплайн): orchestrator + независимые стадии scan/init_db/extract_*/reconcile/report. Каждая стадия должна иметь API и CLI. *depends on 2*.
4. Подготовить системные зависимости для Ubuntu/Debian в prepare.sh. Базовый набор: universal-ctags, cscope, gcc, sqlite3, libsqlite3-dev, pkg-config, ripgrep, git, make. Опционально: clang/llvm для future-validation, но не как обязательная часть MVP. *parallel with 3*.
5. Подготовить Python-зависимости для ./.venv и закрепить команды установки в prepare.sh: click, pydantic, structlog, tree-sitter, tree-sitter-c, pycparser, regex, tqdm, pytest. Все команды установки и запуска **явно** используют `./.venv/bin/python` и `./.venv/bin/pip` — использование системного Python запрещено. *parallel with 3*.
6. Спроектировать оркестратор полного цикла: вход source_root + optional db_path; если db_path не задан, генерировать имя на основе каталога и текущей даты/времени; запуск стадий с подробным логом внешних инструментов и итоговым summary. *depends on 3,4,5*.
7. Подготовить AGENTS.md с внутренним пайплайном ролей (Research/Parser/DB/Reconcile/QA/Docs), входами/выходами, чеклистами качества и правилами эскалации. AGENTS.md **обязан** содержать:
   - предупреждение: нельзя трактовать LOW/MEDIUM как установленный факт без перепроверки `raw_context`;
   - при неоднозначности (`ambiguity_group_id` не NULL) — обязательно брать несколько кандидатов и показывать источник/причину;
   - **явный запрет** на категоричные формулировки в документации при confidence LOW/MEDIUM: вместо «функция X делает Y» писать «по данным индекса (confidence=MEDIUM, detector=ctags), функция X предположительно делает Y; требуется верификация». *depends on 1-6*.
8. Определить верификацию: smoke-прогоны на fixture-деревьях (включая sample/seL4), выборочная ручная проверка сущностей/usage/comment-link, SQL sanity checks, регрессионные тесты парсеров на фикстурах. *depends on 6,7*.

**Relevant files**
- /home/nikolay/work/cagent/PROJECT_TASK.md — исходные требования и границы (Python из ./.venv, prepare.sh, AGENTS.md).
- /home/nikolay/work/cagent/prepare.sh — команды apt и pip для подготовки окружения (будет создан).
- /home/nikolay/work/cagent/AGENTS.md — задания агентам и договоренности по handoff (будет создан).
- /home/nikolay/work/cagent/sample/seL4 — пример fixture-дерева для smoke/regression тестирования, не источник архитектурных зависимостей.
- /home/nikolay/work/cagent/src/orchestrator.py — запуск полного цикла и журналирование (будет создан).
- /home/nikolay/work/cagent/src/db/schema.py — DDL, миграции, индексы, метаданные анализа (будет создан).
- /home/nikolay/work/cagent/src/stages/discover_files.py — реестр анализируемых файлов и hash/метаданные (будет создан).
- /home/nikolay/work/cagent/src/stages/extract_includes.py — граф include и резолв заголовков (будет создан).
- /home/nikolay/work/cagent/src/stages/extract_entities.py — declarations/definitions/scope/type-kind (будет создан).
- /home/nikolay/work/cagent/src/stages/extract_usages.py — reference_candidates (call_candidate/read_write_candidate/macro_expansion_candidate/type_reference_candidate) с полями detector/confidence/ambiguity_group_id/access_kind/scope_distance/candidate_rank (будет создан).
- /home/nikolay/work/cagent/src/stages/extract_comments.py — извлечение комментариев с привязкой preceding/inline и полями detector/confidence (будет создан).
- /home/nikolay/work/cagent/src/stages/extract_preprocessor.py — conditional_regions, preprocessor_symbols, entity_presence_conditions (будет создан).
- /home/nikolay/work/cagent/src/stages/reconcile.py — сопоставление результатов tree-sitter/ctags/cscope/regex; повышение confidence при совпадении источников; пометка конфликтов без удаления спорных записей (будет создан).

**Verification**
1. Подготовка окружения: запуск prepare.sh в Ubuntu/Debian и проверка версий ctags/cscope/gcc/sqlite3/./.venv/bin/python.
2. CLI smoke test: полный прогон оркестратора на /home/nikolay/work/cagent/sample/seL4 с авто-именем БД.
3. SQL sanity checks: количество файлов, includes, entities, usages, comments; отсутствие критичных NULL в ключевых колонках.
4. Точность извлечения: ручная выборка 20 сущностей разных типов, сверка decl/def/usages и привязанных комментариев.
5. Проверка локальности/глобальности: выборка по scope и сравнение на нескольких файлах с static/extern/local.
6. Regression harness: тесты парсеров на фикстурах tricky-case (макросы, typedef function pointer, nested ifdef).

**Decisions**
- Принято: эвристический анализ без compile_commands и без запуска сборки.
- Принято: комментарии связываются как preceding и inline.
- Принято: формат AGENTS.md — роли внутреннего пайплайна (Research/Parser/DB/Reconcile/QA/Docs).
- Включено в MVP: функции, переменные (global/local), типы, define-макросы, includes, reference_candidates, comments, conditional_regions, entity_presence_conditions, include_resolution_attempts.
- Переименовано: `usages` → `reference_candidates` с типами call_candidate/read_write_candidate/macro_expansion_candidate/type_reference_candidate и полем `resolved_entity_id`.
- Добавлено к каждой записи entities/reference_candidates/includes/comments: поля detector, confidence, confidence_reason, raw_context (текст ±3 строки + byte_start/byte_end/line_start/line_end/col_start/col_end), ambiguity_group_id.
- Добавлено к reference_candidates: поля access_kind (read/write/call/type_ref/macro_exp), scope_distance (целое, дистанция от объявления до использования в scope-уровнях), candidate_rank (порядок при нескольких кандидатах на одну позицию) — допустимо NULL на первом этапе.
- Переименовано: стадия `validate_results` → `reconcile` (сопоставление источников + повышение confidence + пометка конфликтов без удаления).
- Исключено из MVP: абсолютная семантическая точность уровня компилятора для всех конфигураций ifdef.
- Принято: sample/seL4 — только тестовый fixture; скрипты и CLI должны быть полностью независимы от seL4 (никаких hardcoded путей/правил под этот проект).

**Further Considerations**
1. Для include-резолва использовать project-root + стандартные include dirs; все кандидаты сохранять в `include_resolution_attempts`; при конфликте — снижать confidence и выставлять `ambiguity_group_id`.
2. Для reference_candidates применять двухпроходную стратегию: быстрый индексатор (ctags/cscope) → стадия reconcile сопоставляет с tree-sitter/regex. Правило confidence взвешенное, не жёсткое: совпадение tree-sitter+ctags может давать HIGH само по себе (tree-sitter надёжнее cscope для сложных конструкций); cscope+regex без tree-sitter — не выше MEDIUM. Итоговое confidence определяется весами источников, а не простым подсчётом.
3. Хранить `raw_context` (сниппет ±3 строки) для всех записей entities/reference_candidates/comments — основа для агентного контекста при документировании и ручной верификации.
4. `conditional_regions` позволяют агентам документации видеть, что сущность существует только при определённых #ifdef — это должно явно отражаться в генерируемой документации (условная доступность, платформо-зависимость).
5. `reconcile.py` не должна ничего удалять — только помечать и повышать/понижать confidence. Это ключевой принцип audit-trail системы.