# AGENTS.md — Руководство для агентов-участников пайплайна

Этот файл описывает роли агентов, работающих с результатами статического анализа
C-кода, хранящимися в SQLite-базе данных.

> **Критичное предупреждение для всех агентов:**
> База данных является **индексом с эвристиками**, а не семантической моделью
> компилятора. Все утверждения должны соответствовать уровню `confidence`
> соответствующей записи. Не допускается утверждать как факт то, что помечено
> `confidence=LOW` или `confidence=MEDIUM`, без явной оговорки об источнике.

---

## Содержание

1. [Research Agent](#1-research-agent)
2. [Parser Agent](#2-parser-agent)
3. [DB Agent](#3-db-agent)
4. [Reconcile Agent](#4-reconcile-agent)
5. [QA Agent](#5-qa-agent)
6. [Docs Agent](#6-docs-agent)
7. [Общие правила для всех агентов](#7-общие-правила-для-всех-агентов)
8. [Таблица уровней confidence](#8-таблица-уровней-confidence)

---

## 1. Research Agent

**Роль:** Исследование кодовой базы по заданному вопросу без изменения БД.

### Входные данные
- Путь к SQLite-файлу.
- Строковый запрос (имя сущности, паттерн, вопрос о структуре).

### Выходные данные
- Структурированный ответ с указанием:
  - `file_path`, `line_start`, `detector`, `confidence`
  - Точной цитатой `raw_context`
  - Перечнем всех `ambiguity_group_id` где применимо

### Чеклист качества
- [ ] Все цитаты взяты из поля `raw_context`, а не из фантазии.
- [ ] Для каждого факта указан `detector` и `confidence`.
- [ ] При `ambiguity_group_id IS NOT NULL` — перечислены все кандидаты группы.
- [ ] Условная доступность (`conditional_regions`) — отражена в ответе.

### Правила эскалации
- Если `confidence=LOW` для ключевого факта → пометить как «требует проверки».
- Если несколько сущностей с одинаковым именем в разных файлах → перечислить все.

---

## 2. Parser Agent

**Роль:** Запуск пайплайна анализа (полностью или по стадиям).

### Входные данные
- `source_root` — корень дерева исходников.
- Опциональный `--db` (иначе авто-генерация).
- Опциональные флаги: `--skip`, `--no-cscope`, `-I`.

### Выходные данные
- Заполненная БД.
- JSON-summary от оркестратора (`src/orchestrator.py`).

### Команда запуска
```bash
./.venv/bin/python -m src.orchestrator <source_dir> [--db <path>] [-v]
```

### Чеклист качества
- [ ] `status` в summary — `ok` или `partial` (не `error`).
- [ ] Поле `total.files` > 0.
- [ ] Поле `total.entities` > 0.
- [ ] В `all_errors` — только некритичные ошибки (например, нечитаемые файлы).

### Правила эскалации
- Если `total.files = 0` → проверить права доступа и расширения файлов.
- Если ctags не найден → прогон не имеет смысла, прервать и сообщить.

---

## 3. DB Agent

**Роль:** Работа со схемой и данными БД: запросы, диагностика, экспорт.

### Входные данные
- Путь к SQLite-файлу.
- SQL-запрос или задание на диагностику.

### Выходные данные
- Результаты запросов в структурированной форме.
- Диагностические выводы с указанием таблиц и полей.

### Полезные запросы

```sql
-- Количество сущностей по detector
SELECT detector, confidence, COUNT(*) FROM entities GROUP BY detector, confidence;

-- Конфликтующие сущности (ambiguity_group_id IS NOT NULL)
SELECT ag.description, e.name, e.detector, e.confidence
FROM entities e
JOIN ambiguity_groups ag ON e.ambiguity_group_id = ag.group_id
ORDER BY ag.group_id;

-- Неразрешённые includes
SELECT count(*) FROM include_resolution_attempts
WHERE resolved_file_id IS NULL;

-- Сущности под условными директивами
SELECT e.name, e.kind, cr.condition_text, cr.depth
FROM entity_presence_conditions epc
JOIN entities e ON epc.entity_id = e.entity_id
JOIN conditional_regions cr ON epc.region_id = cr.region_id
LIMIT 50;
```

### Как находить `call_in` (кто и где вызывает функцию)

Основной источник: view `v_call_in` (строится из `call_sites`).

```sql
-- file:line входящих вызовов функции :func_name в рамках :run_id
SELECT file_path, line_number, caller_name, invoked_name, confidence, macro_names
FROM v_call_in
WHERE run_id = :run_id
   AND callee_name = :func_name
ORDER BY file_path, line_number;
```

Для «чистого» графа (без неоднозначностей и слабых записей):

```sql
SELECT file_path, line_number, caller_name, invoked_name
FROM v_call_in
WHERE run_id = :run_id
   AND callee_name = :func_name
   AND ambiguity_group_id IS NULL
   AND confidence IN ('HIGH', 'MEDIUM')
ORDER BY file_path, line_number;
```

Fallback, если вызовов нет в `v_call_in` (например, извлечение есть только в cscope):

```sql
SELECT f.path AS file_path, rc.line_number, rc.name, rc.detector, rc.confidence
FROM reference_candidates rc
JOIN files f ON f.file_id = rc.file_id
WHERE rc.run_id = :run_id
   AND rc.name = :func_name
   AND rc.candidate_type = 'call_candidate'
ORDER BY f.path, rc.line_number;
```

Правило отчётности:
- Если `v_call_in` и fallback расходятся, указывать это явно и приводить обе выборки.
- В финальном ответе всегда перечислять `file_path:line_number`.

### Как находить переменные: declaration / definition / use

Основной источник declaration/definition: view `v_variable_entities`.

```sql
-- Где объявлена/определена переменная :var_name в рамках :run_id
SELECT file_path, line_start, scope,
          is_declaration, is_definition,
          detector, confidence
FROM v_variable_entities
WHERE run_id = :run_id
   AND variable_name = :var_name
ORDER BY is_definition DESC, file_path, line_start;
```

Основной источник uses: view `v_variable_uses`.

```sql
-- Где используется переменная :var_name (file:line + enclosing function)
SELECT file_path, line_number, enclosing_function,
          access_kind, detector, confidence,
          resolved_file_path, resolved_scope
FROM v_variable_uses
WHERE run_id = :run_id
   AND variable_name = :var_name
ORDER BY file_path, line_number;
```

Для «чистого» отчёта uses (без слабых/неоднозначных):

```sql
SELECT file_path, line_number, enclosing_function, access_kind
FROM v_variable_uses
WHERE run_id = :run_id
   AND variable_name = :var_name
   AND ambiguity_group_id IS NULL
   AND confidence IN ('HIGH', 'MEDIUM')
ORDER BY file_path, line_number;
```

Fallback, если `v_variable_uses` пустой или неполный:

```sql
SELECT f.path AS file_path, rc.line_number,
          rc.name, rc.candidate_type, rc.access_kind,
          rc.detector, rc.confidence
FROM reference_candidates rc
JOIN files f ON f.file_id = rc.file_id
WHERE rc.run_id = :run_id
   AND rc.name = :var_name
   AND rc.candidate_type = 'read_write_candidate'
ORDER BY f.path, rc.line_number;
```

Правило для `static` file-level переменных:
- В отчёте uses всегда показывать `resolved_file_path` и `resolved_scope`.
- Для `scope='static'` использование считается корректно разрешённым только в рамках того же файла (`file_path == resolved_file_path`).

Правило отчётности:
- В финальном ответе всегда давать три секции: `declaration`, `definition`, `uses`.
- Строки uses перечислять в формате `file_path:line_number -- enclosing_function`.
- Если `v_variable_uses` и fallback расходятся, показывать обе выборки и явно помечать расхождение.

### Как находить типы: typedef / chain resolution / use

Основной источник typedef alias-ов: view `v_type_aliases`.

```sql
-- Где объявлен typedef :type_name в рамках :run_id
SELECT file_path, alias_name,
       target_base_name, target_kind,
       indirection_level,
       detector, confidence
FROM v_type_aliases
WHERE run_id = :run_id
   AND alias_name = :type_name
ORDER BY file_path, alias_name;
```

Основной источник chain resolution: view `v_type_resolutions`.

```sql
-- Во что разворачивается typedef :type_name
SELECT file_path, alias_name,
       final_type_name, final_type_kind,
       total_indirection_level,
       is_composite,
       is_cycle, is_ambiguous,
       detector, confidence
FROM v_type_resolutions
WHERE run_id = :run_id
   AND alias_name = :type_name
ORDER BY file_path, alias_name;
```

Основной источник uses: view `v_type_uses`.

```sql
-- Где используется тип :type_name (без локальных переменных)
SELECT file_path, line_number,
       use_context, owner_name,
       by_pointer, indirection_level,
       resolved_final_type_name,
       resolved_final_type_kind,
       resolved_is_composite,
       detector, confidence
FROM v_type_uses
WHERE run_id = :run_id
   AND type_name = :type_name
ORDER BY file_path, line_number;
```

Для «чистого» отчёта uses (без слабых/неоднозначных):

```sql
SELECT file_path, line_number, use_context, owner_name,
       resolved_final_type_name, resolved_final_type_kind
FROM v_type_uses
WHERE run_id = :run_id
   AND type_name = :type_name
   AND ambiguity_group_id IS NULL
   AND confidence IN ('HIGH', 'MEDIUM')
ORDER BY file_path, line_number;
```

Контексты `use_context` в текущей версии:
- `func_param` — параметр функции; `owner_name` = имя функции; `enclosing_function` = имя функции
- `func_return` — возвращаемый тип функции; `owner_name` = имя функции; `enclosing_function` = имя функции
- `global_var` — глобальная переменная; `owner_name` = имя переменной; `enclosing_function` = NULL
- `static_var` — статическая переменная; `owner_name` = имя переменной; `enclosing_function` = NULL
- `field` — поле struct/union; `owner_name` = **имя структуры/union**, имя поля см. в `raw_context`; `enclosing_function` = NULL
- `typedef_target` — правая часть typedef; `owner_name` = имя alias-а; `enclosing_function` = NULL
- `local_var` — локальная переменная в теле функции; `owner_name` = имя переменной; `enclosing_function` = **имя функции**

### Как найти все struct/union, использующие тип как поле

```sql
-- В каких структурах/union тип :type_name используется как поле
SELECT DISTINCT owner_name AS struct_name,
       by_pointer, resolved_final_type_name
FROM v_type_uses
WHERE run_id = :run_id
   AND type_name = :type_name
   AND use_context = 'field'
ORDER BY struct_name;
```

Для просмотра полного контекста каждого поля (имя поля в `raw_context`):

```sql
SELECT owner_name AS struct_name,
       file_path, line_number,
       by_pointer, raw_context
FROM v_type_uses
WHERE run_id = :run_id
   AND type_name = :type_name
   AND use_context = 'field'
ORDER BY struct_name, file_path, line_number;
```

Ограничения текущей версии:
- Для `use_context='field'` при объявлении нескольких полей одной строкой (`tcb_t *head, *end;`) создаётся одна запись (первый декларатор); детали — в `raw_context`.

### Как найти функции, использующие тип как локальную переменную

```sql
-- В каких функциях тип :type_name объявляется как локальная переменная
SELECT DISTINCT enclosing_function,
       file_path
FROM v_type_uses
WHERE run_id = :run_id
   AND type_name = :type_name
   AND use_context = 'local_var'
ORDER BY file_path, enclosing_function;
```

Для просмотра контекста объявления (имя переменной + фрагмент кода):

```sql
SELECT enclosing_function, file_path, line_number,
       owner_name AS var_name,
       by_pointer, raw_context
FROM v_type_uses
WHERE run_id = :run_id
   AND type_name = :type_name
   AND use_context = 'local_var'
ORDER BY file_path, line_number;
```

Правило отчётности:
- В финальном ответе всегда давать три секции: `typedef`, `resolution`, `uses`.
- Строки uses перечислять в формате `file_path:line_number -- use_context -- owner_name`.
- Для `LOW` и `MEDIUM` обязательно указывать, что вывод индексный и требует верификации.

### Чеклист качества
- [ ] Никогда не выполнять `DELETE`, `DROP`, `UPDATE` без явного задания.
- [ ] При экспорте — включать `detector`, `confidence`, `raw_context`.
- [ ] Не фильтровать записи с `confidence=LOW` по умолчанию — они нужны для аудита.

---

## 4. Reconcile Agent

**Роль:** Дополнительная сверка после базового `reconcile` стадии.
Используется когда нужно применить domain-специфичные правила поверх общих.

### Входные данные
- Путь к SQLite-файлу и `run_id`.
- Правила сверки (в виде SQL или Python-скриптов).

### Выходные данные
- Обновлённые значения `confidence`, `confidence_reason`, `ambiguity_group_id`.
- Никакие записи не удаляются.

### Чеклист качества
- [ ] Каждое изменение `confidence` сопровождается обновлением `confidence_reason`.
- [ ] При создании `ambiguity_group` — заполнять поле `description` осмысленно.
- [ ] Запуск идемпотентен: повторный запуск не создаёт дублей.

### Правила эскалации
- Если для одного имени > 5 кандидатов → вынести на проверку человеком.

---

## 5. QA Agent

**Роль:** Проверка полноты и согласованности данных в БД.

### Входные данные
- Путь к SQLite-файлу.
- Опционально: конкретная стадия или таблица для проверки.

### Проверки

```sql
-- Orphaned entities (нет файла)
SELECT COUNT(*) FROM entities e
LEFT JOIN files f ON e.file_id = f.file_id
WHERE f.file_id IS NULL;

-- References без resolved_entity_id (нормально, но отслеживать %)
SELECT detector,
       COUNT(*) as total,
       SUM(CASE WHEN resolved_entity_id IS NULL THEN 1 ELSE 0 END) as unresolved
FROM reference_candidates
GROUP BY detector;

-- Сущности без комментариев
SELECT kind, COUNT(*) FROM entities e
WHERE e.entity_id NOT IN (SELECT entity_id FROM entity_comments)
GROUP BY kind;
```

### Чеклист качества
- [ ] 0 orphaned entities (сущности без файла).
- [ ] `analysis_runs.finished_at IS NOT NULL` для завершённых прогонов.
- [ ] Все стадии в `stages_completed` поля `analysis_runs`.
- [ ] Процент `LOW` confidence < 80% от всех entities (иначе что-то пошло не так).

### Правила эскалации
- > 1000 errors в `all_errors` → сигнализировать о проблеме с исходниками.
- 0 entities при наличии файлов → ctags не запустился или не нашёл C-кода.

---

## 6. Docs Agent

**Роль:** Генерация документации на основе данных БД.

> ### ⚠ ОБЯЗАТЕЛЬНЫЕ ПРЕДУПРЕЖДЕНИЯ
>
> **1. Запрет на категоричный язык для LOW/MEDIUM:**
>
> Вместо:
> > «Функция `X` делает Y.»
>
> Необходимо:
> > «По данным индекса (confidence=MEDIUM, detector=ctags), функция `X`
> > предположительно делает Y; требуется верификация по `raw_context`.»
>
> **2. При `ambiguity_group_id IS NOT NULL` — ОБЯЗАТЕЛЕН список кандидатов:**
>
> Нельзя выбрать один вариант из группы без явного указания всех.
> Все записи группы должны быть перечислены с их `detector` и `confidence`.
>
> **3. Условная доступность:**
>
> Если сущность присутствует в `entity_presence_conditions` → документация
> ДОЛЖНА отражать, что сущность доступна только при выполнении условия
> `condition_text` (например, `#ifdef CONFIG_ARM`).
>
> **4. Нет данных = нет утверждения:**
>
> Если поле `raw_context` пустое или NULL → нельзя цитировать контекст.
> Нельзя домысливать назначение функции по одному имени.

### Входные данные
- Путь к SQLite-файлу.
- Задание: описать сущность / модуль / паттерн.

### Выходные данные
- Markdown-документ с явным указанием уровня достоверности каждого утверждения.
- Таблица сущностей модуля с колонками: `name`, `kind`, `confidence`, `detector`.
- Список TODO-пунктов для ручной верификации LOW-confidence фактов.

### Пример корректного вывода

```markdown
## `seL4_Send` (confidence=HIGH, detector=ctags)

> Источник: `src/api/syscall.c:42`
> raw_context:
> ```c
> void seL4_Send(seL4_CPtr dest, seL4_MessageInfo_t msgInfo) {
> ```

По данным ctags (confidence=HIGH), функция `seL4_Send` объявлена как
принимающая два аргумента: `seL4_CPtr dest` и `seL4_MessageInfo_t msgInfo`.

⚠ **Условная доступность:** присутствует только при `CONFIG_KERNEL_MCS=0`
(см. `entity_presence_conditions`).

⚠ **Требует верификации (TODO):** описание поведения отсутствует в индексе
(комментариев к функции не найдено — `entity_comments` пуст для этой сущности).
```

### Чеклист качества
- [ ] Каждое утверждение сопровождается `confidence` и `detector`.
- [ ] Все `ambiguity_group_id IS NOT NULL` — раскрыты.
- [ ] Условные сущности помечены явно.
- [ ] LOW-confidence факты в секции TODO / «требует проверки».
- [ ] Нет цитирования несуществующего `raw_context`.

### Правила эскалации
- Если для описываемой сущности все записи `confidence=LOW` → вынести весь
  раздел в «непроверенные», не в основную документацию.
- Если `entity_comments` пуст для сущности → не генерировать описание поведения,
  только сигнатуру.

---

## 7. Общие правила для всех агентов

1. **Не модифицировать исходники.** Агенты работают только с БД и выходными
   артефактами.
2. **Не удалять записи из БД.** Любая правка — только UPDATE с пояснением.
3. **Использовать `run_id` при запросах.** Запросы без `WHERE run_id = ?`
   могут смешивать данные разных прогонов.
4. **Audit-trail обязателен.** При любом изменении confidence — обновлять
   `confidence_reason`.
5. **Нет project-specific hardcoding.** Скрипты и запросы не должны содержать
   имён конкретных проектов, файлов или символов. Параметризуй через CLI/API.
6. **Heuristic-only база.** Индекс создан без полного разбора AST и без
   compile_commands.json. Это не замена компилятору.

---

## 8. Таблица уровней confidence

| Уровень   | Значение                                                | Основные источники           |
|-----------|--------------------------------------------------------|------------------------------|
| `HIGH`    | Несколько надёжных детекторов согласны, или ctags+tree_sitter | ctags, tree_sitter, их сочетание |
| `MEDIUM`  | Один надёжный детектор или несколько слабых            | cscope, ctags в одиночку     |
| `LOW`     | Только эвристика (regex) или один слабый детектор      | regex, manual_rule           |

**Правило уровня:** `confidence` никогда не повышается выше `MEDIUM` если
в группе есть только `cscope` и `regex` (нет `ctags` или `tree_sitter`).

---

*Обновляй этот файл при добавлении новых детекторов или изменении схемы БД.*
