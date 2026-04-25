# DB.md — Описание схемы базы данных

База данных — **эвристический индекс C-кода**, а не семантическая модель компилятора.
Все утверждения трассируемы: каждая запись несёт поля `detector`, `confidence`,
`confidence_reason` и `raw_context`.

Файл БД создаётся оркестратором (`src/orchestrator.py`) и заполняется стадиями
в следующем порядке:
`discover_files → extract_includes → extract_entities → extract_comments →
extract_preprocessor → extract_usages → reconcile`

---

## Содержание

1. [analysis_runs](#1-analysis_runs)
2. [files](#2-files)
3. [ambiguity_groups](#3-ambiguity_groups)
4. [entities](#4-entities)
5. [includes](#5-includes)
6. [include_resolution_attempts](#6-include_resolution_attempts)
7. [comments](#7-comments)
8. [entity_comments](#8-entity_comments)
9. [reference_candidates](#9-reference_candidates)
10. [call_sites](#10-call_sites)
11. [conditional_regions](#11-conditional_regions)
12. [preprocessor_symbols](#12-preprocessor_symbols)
13. [entity_presence_conditions](#13-entity_presence_conditions)
14. [Поля трассировки — общий глоссарий](#14-поля-трассировки--общий-глоссарий)
15. [Значения confidence](#15-значения-confidence)
16. [Значения detector](#16-значения-detector)
17. [SQL Views](#17-sql-views)

---

## 1. `analysis_runs`

Метаданные каждого прогона пайплайна. Один прогон = один полный или частичный
запуск оркестратора над деревом исходников.

| Колонка            | Тип     | Назначение |
|--------------------|---------|------------|
| `run_id`           | INTEGER | PK, автоинкремент. Внешний ключ для всех таблиц данных. |
| `source_root`      | TEXT    | Абсолютный путь к корню дерева исходников. |
| `db_path`          | TEXT    | Абсолютный путь к файлу БД на момент прогона. |
| `started_at`       | TEXT    | ISO-8601 timestamp начала прогона (UTC). |
| `finished_at`      | TEXT    | ISO-8601 timestamp завершения. NULL если прогон не завершился. |
| `pipeline_version` | TEXT    | Версия пайплайна (например, `'1.0.0'`). |
| `stages_completed` | TEXT    | JSON-массив имён завершённых стадий, например `["discover_files","extract_entities"]`. |
| `total_files`      | INTEGER | Итоговое кол-во файлов (заполняется `finish_run`). |
| `total_entities`   | INTEGER | Итоговое кол-во сущностей. |
| `total_references` | INTEGER | Итоговое кол-во кандидатов на использования. |
| `total_comments`   | INTEGER | Итоговое кол-во комментариев. |
| `total_includes`   | INTEGER | Итоговое кол-во #include-директив. |
| `errors`           | TEXT    | JSON-массив ошибок формата `[{stage, error}, ...]`. NULL если ошибок нет. |

> **Правило:** всегда фильтруй запросы по `run_id`. Несколько прогонов над одним
> деревом хранятся в одной БД и могут конкурировать.

---

## 2. `files`

Инвентарь C-файлов и заголовков, найденных в `source_root`.
Заполняется стадией `discover_files`.

| Колонка         | Тип     | Назначение |
|-----------------|---------|------------|
| `file_id`       | INTEGER | PK. |
| `run_id`        | INTEGER | FK → `analysis_runs`. |
| `path`          | TEXT    | Путь относительно `source_root`. Уникален внутри одного `run_id`. |
| `absolute_path` | TEXT    | Абсолютный путь к файлу. Используется при чтении содержимого другими стадиями. |
| `size_bytes`    | INTEGER | Размер файла в байтах на момент прогона. |
| `sha256`        | TEXT    | SHA-256 hex-дайджест содержимого. Позволяет обнаруживать изменения. |
| `is_header`     | INTEGER | 1 если расширение файла — заголовочный (`.h`, `.hpp` и т.п.), 0 иначе. |
| `language`      | TEXT    | Язык файла, по умолчанию `'c'`. |

Индексы: `(run_id)`, `(run_id, path)`.

---

## 3. `ambiguity_groups`

Группы неоднозначности. Создаются стадией `reconcile`, когда несколько
детекторов дают конкурирующие интерпретации одной позиции в коде.

| Колонка       | Тип     | Назначение |
|---------------|---------|------------|
| `group_id`    | INTEGER | PK. |
| `run_id`      | INTEGER | FK → `analysis_runs`. |
| `description` | TEXT    | Человекочитаемое описание конфликта: имя сущности, файл, строка, список детекторов. |
| `created_at`  | TEXT    | Timestamp создания группы. |

Записи, принадлежащие группе, имеют `ambiguity_group_id IS NOT NULL` в своей
таблице (`entities` или `reference_candidates`).

---

## 4. `entities`

Объявления и определения C-сущностей: функции, переменные, типы, макросы и т.д.
Основная таблица. Заполняется стадией `extract_entities` (ctags), дополняется
reconcile-стадией.

### Позиция и вид

| Колонка           | Тип     | Назначение |
|-------------------|---------|------------|
| `entity_id`       | INTEGER | PK. |
| `run_id`          | INTEGER | FK → `analysis_runs`. |
| `file_id`         | INTEGER | FK → `files`. |
| `name`            | TEXT    | Имя сущности (идентификатор). |
| `kind`            | TEXT    | Вид сущности. Допустимые значения: `function`, `variable`, `typedef`, `struct`, `union`, `enum`, `enumerator`, `macro`, `field`, `label`, `prototype`. |
| `scope`           | TEXT    | Область видимости: `global`, `static`, `local`, `extern`, `parameter`. NULL если не определено. |
| `line_start`      | INTEGER | Номер строки начала (1-based). |
| `col_start`       | INTEGER | Колонка начала (1-based). NULL если детектор не предоставил. |
| `line_end`        | INTEGER | Номер строки конца. NULL если неизвестно. |
| `col_end`         | INTEGER | Колонка конца. NULL если неизвестно. |
| `byte_start`      | INTEGER | Байтовое смещение начала в файле. NULL если неизвестно. |
| `byte_end`        | INTEGER | Байтовое смещение конца в файле. NULL если неизвестно. |
| `signature`       | TEXT    | Текстовая сигнатура: для функции — список параметров, для переменной — тип и т.п. NULL если недоступно. |
| `is_declaration`  | INTEGER | 1 если запись является объявлением (прототип, extern-декларация), 0 иначе. |
| `is_definition`   | INTEGER | 1 если запись является определением, 0 иначе. Одна и та же сущность может иметь несколько записей с разным флагом. |
| `parent_entity_id`| INTEGER | FK → `entities`. Заполняется для полей структур (`field`) и вложенных типов. |

### Поля трассировки

| Колонка               | Назначение |
|-----------------------|------------|
| `detector`            | Источник записи. Чаще всего `'ctags'`. |
| `confidence`          | `HIGH` / `MEDIUM` / `LOW`. |
| `confidence_reason`   | Текстовое объяснение оценки уверенности. |
| `raw_context`         | ±3 строки вокруг позиции сущности в исходнике. |
| `raw_context_line_start/end` | Строки, которые покрывает `raw_context`. |
| `raw_context_byte_start/end` | Байтовые смещения диапазона `raw_context`. |
| `ambiguity_group_id`  | FK → `ambiguity_groups`. NULL если сущность однозначна. |

Индексы: `(name)`, `(file_id)`, `(kind, scope)`, `(run_id)`, `(confidence)`.

---

## 5. `includes`

`#include`-директивы, найденные в файлах. Заполняется стадией `extract_includes`.

| Колонка            | Тип     | Назначение |
|--------------------|---------|------------|
| `include_id`       | INTEGER | PK. |
| `run_id`           | INTEGER | FK → `analysis_runs`. |
| `source_file_id`   | INTEGER | FK → `files`. Файл, содержащий директиву. |
| `line_number`      | INTEGER | Номер строки с `#include`. |
| `include_path`     | TEXT    | Литерал пути как написано в коде: `"foo/bar.h"` или `<stdint.h>`. |
| `include_type`     | TEXT    | `quoted` (кавычки `""`) или `angled` (угловые скобки `<>`). |
| `resolved_file_id` | INTEGER | FK → `files`. Файл, к которому разрешился include. NULL если не найден в дереве. |
| `is_resolved`      | INTEGER | 1 если `resolved_file_id` заполнен. |
| Поля трассировки   | —       | `detector='regex'`, `confidence` зависит от числа кандидатов (см. ниже). |

**Семантика confidence для includes:**
- `HIGH` — единственный кандидат найден.
- `MEDIUM` — несколько файлов с подходящим именем, выбран первый.
- `LOW` — файл не найден ни в одном из путей поиска.

Все попытки поиска (включая неудачные) хранятся в `include_resolution_attempts`.

Индексы: `(source_file_id)`, `(resolved_file_id)`, `(run_id)`.

---

## 6. `include_resolution_attempts`

Полный журнал попыток разрешить `#include`. Хранит **все** кандидатские пути,
а не только победивший. Используется для аудита и диагностики.

| Колонка          | Тип     | Назначение |
|------------------|---------|------------|
| `attempt_id`     | INTEGER | PK. |
| `include_id`     | INTEGER | FK → `includes`. |
| `candidate_path` | TEXT    | Абсолютный путь кандидата, который проверялся. |
| `search_dir`     | TEXT    | Директория, из которой велась попытка разрешения. |
| `resolved`       | INTEGER | 1 если этот кандидат был выбран как итоговый. |

---

## 7. `comments`

Комментарии (`/* ... */` и `// ...`), извлечённые из исходников.
Заполняется стадией `extract_comments`. Детектор: `regex`.

| Колонка        | Тип     | Назначение |
|----------------|---------|------------|
| `comment_id`   | INTEGER | PK. |
| `run_id`       | INTEGER | FK → `analysis_runs`. |
| `file_id`      | INTEGER | FK → `files`. |
| `line_start`   | INTEGER | Первая строка комментария (1-based). |
| `line_end`     | INTEGER | Последняя строка комментария. |
| `col_start`    | INTEGER | Колонка начала. |
| `col_end`      | INTEGER | Колонка конца. |
| `byte_start`   | INTEGER | Байтовое смещение начала `/*` или `//`. |
| `byte_end`     | INTEGER | Байтовое смещение конца комментария. |
| `text`         | TEXT    | Полный текст комментария, включая маркеры `/*`, `*/`, `//`. |
| `comment_type` | TEXT    | `line_comment` (однострочный `//`) или `block_comment` (многострочный `/* */`). |
| Поля трассировки | —     | `detector='regex'`, `confidence='HIGH'` (regex для комментариев надёжен). |

Индексы: `(file_id)`, `(file_id, line_start)`.

---

## 8. `entity_comments`

Таблица связи комментариев с сущностями. Одна запись = одна ассоциация.
Заполняется стадией `extract_comments` после вставки комментариев.

| Колонка            | Тип     | Назначение |
|--------------------|---------|------------|
| `entity_id`        | INTEGER | FK → `entities`. |
| `comment_id`       | INTEGER | FK → `comments`. |
| `association_type` | TEXT    | `preceding` — комментарий находится прямо перед сущностью; `inline` — на той же строке. |
| `distance_lines`   | INTEGER | Количество строк между концом комментария и началом сущности. Для `inline` = 0. |

PK: `(entity_id, comment_id)`.

**Семантика `preceding`:** комментарий считается документирующим, если его конец
находится в пределах `preceding_gap` строк (по умолчанию 2) от начала сущности,
и между ними нет кода.

---

## 9. `reference_candidates`

Кандидаты на использования сущностей в коде. Не являются подтверждёнными
ссылками — это эвристические «подозреваемые», требующие верификации.
Заполняется стадией `extract_usages` (cscope + regex).

### Позиция и классификация

| Колонка             | Тип     | Назначение |
|---------------------|---------|------------|
| `ref_id`            | INTEGER | PK. |
| `run_id`            | INTEGER | FK → `analysis_runs`. |
| `file_id`           | INTEGER | FK → `files`. |
| `name`              | TEXT    | Имя сущности, на которую предположительно ссылается запись. |
| `line_number`       | INTEGER | Номер строки использования. |
| `col_start`         | INTEGER | Колонка начала имени (1-based). NULL для cscope (не предоставляет). |
| `col_end`           | INTEGER | Колонка конца имени. NULL для cscope. |
| `byte_start`        | INTEGER | Байтовое смещение начала. NULL если не определено. |
| `byte_end`          | INTEGER | Байтовое смещение конца. NULL если не определено. |
| `candidate_type`    | TEXT    | Тип использования (эвристика): `call_candidate`, `read_write_candidate`, `macro_expansion_candidate`, `type_reference_candidate`. |
| `access_kind`       | TEXT    | Уточнение: `call`, `read`, `write`, `type_ref`, `macro_exp`. NULL допустимо. |
| `resolved_entity_id`| INTEGER | FK → `entities`. Если имя однозначно совпадает с известной сущностью — заполняется. NULL = не разрешено. |
| `scope_distance`    | INTEGER | Дистанция между объявлением и использованием в уровнях вложенности scope. Заполняется reconcile. |
| `candidate_rank`    | INTEGER | Ранг записи среди кандидатов на одну позицию (1 = наиболее надёжный детектор). Заполняется reconcile. |

### Поля трассировки

| Колонка                  | Назначение |
|--------------------------|------------|
| `detector`               | `'cscope'` или `'regex'`. |
| `confidence`             | `MEDIUM` для cscope, `LOW` для regex (до reconcile). |
| `confidence_reason`      | Причина оценки. |
| `raw_context`            | ±3 строки вокруг строки использования. |
| `raw_context_line_start/end`  | Строковый диапазон `raw_context`. |
| `raw_context_col_start/end`   | Дополнительные колонки диапазона (специфично для `reference_candidates`). |
| `raw_context_byte_start/end`  | Байтовый диапазон `raw_context`. |
| `ambiguity_group_id`     | FK → `ambiguity_groups`. Заполняется reconcile при конфликте `candidate_type`. |

Индексы: `(name)`, `(file_id)`, `(resolved_entity_id)`, `(run_id)`, `(confidence)`.

---

## 10. `call_sites`

Явные точки вызова функций, извлечённые из AST через `tree-sitter-c` на стадии
`extract_entities`. Это основной источник для построения `call_in` / `call_out`.

| Колонка           | Тип     | Назначение |
|-------------------|---------|------------|
| `call_id`         | INTEGER | PK. |
| `run_id`          | INTEGER | FK → `analysis_runs`. |
| `file_id`         | INTEGER | FK → `files`. |
| `caller_entity_id`| INTEGER | FK → `entities`. Функция, внутри которой находится вызов. NULL если caller не удалось сопоставить с записью `entities`. |
| `caller_name`     | TEXT    | Имя caller-функции для удобства запросов и диагностики. |
| `callee_entity_id`| INTEGER | FK → `entities`. Целевая функция, если удалось однозначно разрешить. |
| `callee_name`     | TEXT    | Итоговое имя целевой функции после разворачивания макро-обёрток, если это удалось. |
| `invoked_name`    | TEXT    | Имя, вызванное непосредственно в исходнике. Может быть именем макроса-обёртки, а не конечной функции. |
| `call_text`       | TEXT    | Полный текст выражения вызова, например `INVOKE(x)` или `seL4_Send(dest, msg)`. |
| `line_number`     | INTEGER | Строка вызова (1-based). |
| `col_start`       | INTEGER | Колонка начала выражения вызова (1-based). |
| `col_end`         | INTEGER | Колонка конца выражения вызова. |
| `byte_start`      | INTEGER | Байтовое смещение начала call expression. |
| `byte_end`        | INTEGER | Байтовое смещение конца call expression. |
| `macro_names`     | TEXT    | JSON-массив function-like макросов, через которые реализован вызов. Например `["INVOKE","WRAP"]`. NULL для прямого вызова. |
| `detector`        | TEXT    | Сейчас `tree_sitter`. |
| `confidence`      | TEXT    | `HIGH` для прямого или успешно развёрнутого macro-call с разрешённым callee, `MEDIUM` для частично разрешённых случаев. |
| `confidence_reason` | TEXT  | Причина оценки. |
| `raw_context`     | TEXT    | ±3 строки вокруг вызова. |
| `raw_context_line_start/end` | INTEGER | Диапазон строк `raw_context`. |
| `raw_context_byte_start/end` | INTEGER | Байтовый диапазон `raw_context`. |
| `ambiguity_group_id` | INTEGER | FK → `ambiguity_groups`. Пока обычно NULL; зарезервировано для reconcile вызовов. |

Индексы: `(run_id)`, `(file_id)`, `(caller_entity_id)`, `(callee_entity_id)`.

Практическое применение:
- `call_in`: выбрать `call_sites` по `callee_entity_id` или `callee_name`.
- `call_out`: выбрать `call_sites` по `caller_entity_id` или `caller_name`.
- При macro-mediated вызовах использовать `invoked_name` и `macro_names`, чтобы видеть и исходный токен вызова, и цепочку обёрток.

После стадии `reconcile` для `call_sites` дополнительно нормализуются:
- `confidence`
- `confidence_reason`
- `ambiguity_group_id`

Правила reconcile для вызовов:
- прямой вызов с однозначно разрешённым `callee_entity_id` получает `HIGH`
- macro-mediated вызов с однозначно разрешённым terminal callee тоже получает `HIGH`
- unresolved direct call остаётся `MEDIUM`
- conflicting callees на одной и той же позиции помечаются через `ambiguity_group_id`

---

## 11. `conditional_regions`

Регионы условной компиляции: `#if`, `#ifdef`, `#ifndef`, `#elif`, `#else`, `#endif`.
Строится как дерево с вложенностью. Заполняется стадией `extract_preprocessor`.

| Колонка           | Тип     | Назначение |
|-------------------|---------|------------|
| `region_id`       | INTEGER | PK. |
| `run_id`          | INTEGER | FK → `analysis_runs`. |
| `file_id`         | INTEGER | FK → `files`. |
| `directive`       | TEXT    | Имя директивы: `if`, `ifdef`, `ifndef`, `elif`, `else`, `endif`. |
| `condition`       | TEXT    | Текст условия (например, `CONFIG_ARM`, `defined(SMP) && N_CPUS > 1`). NULL для `else`/`endif`. |
| `line_start`      | INTEGER | Строка директивы открытия. |
| `line_end`        | INTEGER | Строка закрывающего `endif`. NULL если `endif` не найден (незакрытый регион). |
| `depth`           | INTEGER | Уровень вложенности (0 = верхний уровень). |
| `parent_region_id`| INTEGER | FK → `conditional_regions`. PK родительского региона. NULL для регионов верхнего уровня. |

Индексы: `(file_id)`, `(run_id)`.

---

## 12. `preprocessor_symbols`

Макросы и символы препроцессора: `#define`, `#undef`, include guards.
Заполняется стадией `extract_preprocessor`.

| Колонка                | Тип     | Назначение |
|------------------------|---------|------------|
| `symbol_id`            | INTEGER | PK. |
| `run_id`               | INTEGER | FK → `analysis_runs`. |
| `file_id`              | INTEGER | FK → `files`. |
| `name`                 | TEXT    | Имя символа (`FOO`, `MAX_SIZE` и т.п.). |
| `symbol_type`          | TEXT    | `define`, `undef`, `include_guard`. |
| `line_number`          | INTEGER | Строка директивы. |
| `value`                | TEXT    | Тело подстановки для `#define`. NULL для `#undef` и include guards. |
| `params`               | TEXT    | JSON-массив параметров для function-like макросов (например, `["x","y"]`). NULL для object-like. |
| `is_function_like`     | INTEGER | 1 если макрос принимает параметры (`#define FOO(x) ...`), 0 иначе. |
| `conditional_region_id`| INTEGER | FK → `conditional_regions`. Регион, внутри которого определён символ. NULL если на верхнем уровне. |

Индексы: `(name)`, `(file_id)`.

---

## 13. `entity_presence_conditions`

Связь сущности с условными регионами: «эта сущность доступна только если
выполняется данное условие». Заполняется стадией `extract_preprocessor`
после построения дерева регионов.

| Колонка                | Тип     | Назначение |
|------------------------|---------|------------|
| `epc_id`               | INTEGER | PK. |
| `entity_id`            | INTEGER | FK → `entities`. |
| `conditional_region_id`| INTEGER | FK → `conditional_regions`. |
| `condition_text`       | TEXT    | Текст условия (копия из `conditional_regions.condition` для удобства). |

Индекс: `(entity_id)`.

> **Важно для Docs Agent:** если для сущности есть запись в этой таблице,
> документация **обязана** отражать, что сущность условно доступна
> (например: «доступна только при `#ifdef CONFIG_ARM`»).

---

## 14. Поля трассировки — общий глоссарий

Следующие поля присутствуют в большинстве таблиц данных:

| Поле                      | Тип  | Назначение |
|---------------------------|------|------------|
| `detector`                | TEXT | Источник записи. Значения: `ctags`, `cscope`, `tree_sitter`, `regex`, `manual_rule`. |
| `confidence`              | TEXT | Уровень уверенности: `HIGH`, `MEDIUM`, `LOW`. |
| `confidence_reason`       | TEXT | Текстовое объяснение, почему выставлен данный уровень. Обновляется при reconcile. |
| `raw_context`             | TEXT | Текст ±3 строк вокруг позиции записи в исходном файле. NULL если файл недоступен. |
| `raw_context_line_start`  | INT  | Первая строка диапазона `raw_context` (1-based). |
| `raw_context_line_end`    | INT  | Последняя строка диапазона `raw_context` (1-based). |
| `raw_context_byte_start`  | INT  | Байтовое смещение начала `raw_context`. |
| `raw_context_byte_end`    | INT  | Байтовое смещение конца `raw_context`. |
| `ambiguity_group_id`      | INT  | FK → `ambiguity_groups`. NULL = запись однозначна. Не NULL = конфликт с другими записями. |

---

## 15. Значения `confidence`

| Значение | Интерпретация |
|----------|---------------|
| `HIGH`   | Несколько надёжных детекторов согласны, или ctags+tree_sitter в паре. Можно цитировать без оговорок. |
| `MEDIUM` | Один надёжный детектор (`ctags` в одиночку, `cscope`). Требует оговорки об источнике. |
| `LOW`    | Только эвристика (`regex`, `manual_rule`) или один слабый детектор. Обязательна пометка «требует верификации». |

**Правило повышения:** `confidence` не может подняться выше `MEDIUM`, если
в группе присутствуют только `cscope` и `regex` (нет `ctags` или `tree_sitter`).

---

## 16. Значения `detector`

| Значение      | Инструмент           | Надёжность | Стадия              |
|---------------|----------------------|------------|---------------------|
| `ctags`       | universal-ctags      | Высокая    | extract_entities    |
| `tree_sitter` | tree-sitter-c        | Высокая    | extract_entities, extract_types |
| `cscope`      | cscope               | Средняя    | extract_usages      |
| `regex`       | Python `re`          | Низкая     | все стадии          |
| `manual_rule` | ручное правило       | Переменная | reconcile           |

---

## 17. SQL Views

В схеме создаются следующие SQL-view:
- `v_call_edges`
- `v_call_in`
- `v_call_out`
- `v_variable_entities`
- `v_variable_uses`
- `v_type_aliases`
- `v_type_resolutions`
- `v_type_uses`

Ниже приведено назначение каждого view и примеры запросов.

### `v_call_edges`

Нормализованный enriched view поверх `call_sites`, `files`, `entities`.
Содержит:
- `caller_name`, `caller_signature`
- `callee_name`, `callee_signature`
- `file_path`
- координаты вызова, `macro_names`, `confidence`, `raw_context`

Пример:

```sql
SELECT *
FROM v_call_edges
WHERE run_id = :run_id
  AND callee_name = 'seL4_Send';
```

### `v_call_in`

Ориентация на входящие вызовы: кто вызывает данную функцию.

Пример:

```sql
SELECT caller_name, file_path, line_number, call_text, macro_names, confidence
FROM v_call_in
WHERE run_id = :run_id
  AND callee_name = :func_name
ORDER BY caller_name, file_path, line_number;
```

### `v_call_out`

Ориентация на исходящие вызовы: кого вызывает данная функция.

Пример:

```sql
SELECT callee_name, file_path, line_number, call_text, macro_names, confidence
FROM v_call_out
WHERE run_id = :run_id
  AND caller_name = :func_name
ORDER BY callee_name, file_path, line_number;
```

### `v_variable_entities`

View над `entities` (только `kind='variable'`) с удобным доступом к месту
объявления/определения переменной.

Содержит:
- `variable_name`, `file_path`, `line_start`
- `scope`
- `is_declaration`, `is_definition`
- `detector`, `confidence`, `confidence_reason`

Пример:

```sql
SELECT variable_name, file_path, line_start,
       is_declaration, is_definition,
       scope, detector, confidence
FROM v_variable_entities
WHERE run_id = :run_id
  AND variable_name = :var_name
ORDER BY is_definition DESC, file_path, line_start;
```

### `v_variable_uses`

View над `reference_candidates` для uses переменных (только
`candidate_type='read_write_candidate'`) с привязкой к файлу использования,
возможному resolved declaration/definition и enclosing function.

Содержит:
- `variable_name`, `file_path`, `line_number`
- `enclosing_function`
- `access_kind` (`read` / `write`)
- `resolved_entity_id`, `resolved_file_path`, `resolved_scope`
- `detector`, `confidence`, `confidence_reason`

Пример:

```sql
SELECT file_path, line_number, enclosing_function,
       access_kind, resolved_file_path, resolved_scope,
       detector, confidence
FROM v_variable_uses
WHERE run_id = :run_id
  AND variable_name = :var_name
ORDER BY file_path, line_number;
```

Для `static` file-level переменных полезно проверять, что использование остаётся
в пределах того же файла определения:

```sql
SELECT file_path, line_number, resolved_file_path, resolved_scope
FROM v_variable_uses
WHERE run_id = :run_id
  AND variable_name = :var_name
  AND resolved_scope = 'static'
  AND file_path != resolved_file_path;
```

Если запрос вернул строки, это кандидаты на неверный резолв `static`-переменной.

Если нужен только надёжный graph, добавляй фильтр:

```sql
AND confidence = 'HIGH'
AND ambiguity_group_id IS NULL
```

### `v_type_aliases`

View над `type_aliases` для typedef alias-записей (`alias -> target`).

Содержит:
- `alias_name`, `target_base_name`, `target_kind`
- `indirection_level`
- `file_path`
- `detector`, `confidence`, `confidence_reason`
- `raw_context`, `ambiguity_group_id`

Пример:

```sql
SELECT file_path, alias_name,
       target_base_name, target_kind,
       indirection_level,
       detector, confidence
FROM v_type_aliases
WHERE run_id = :run_id
  AND alias_name = :type_name
ORDER BY file_path, alias_name;
```

### `v_type_resolutions`

View над `type_resolutions` для результатов разворачивания typedef-цепочек.

Содержит:
- `alias_name`
- `final_type_name`, `final_type_kind`
- `total_indirection_level`
- `is_composite`, `is_cycle`, `is_ambiguous`
- `resolution_path`
- `detector`, `confidence`, `confidence_reason`
- `file_path`

Пример:

```sql
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

### `v_type_uses`

View над `type_uses` для использований типа в сигнатурах и non-local декларациях.

Содержит:
- `type_name`, `file_path`, `line_number`
- `use_context` (`func_param`, `func_return`, `global_var`, `static_var`, `field`, `typedef_target`)
- `owner_name` — семантика зависит от `use_context`:
  - `func_param` / `func_return` → имя функции
  - `global_var` / `static_var` → имя переменной
  - `field` → **имя содержащей структуры/union** (тег); имя поля см. в `raw_context`
  - `typedef_target` → имя alias-а
- `by_pointer`, `indirection_level`
- `resolved_final_type_name`, `resolved_final_type_kind`, `resolved_is_composite`
- `detector`, `confidence`, `confidence_reason`, `ambiguity_group_id`

Пример:

```sql
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

Для надёжной выборки без неоднозначностей:

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

Для поиска структур/union, в которых тип используется как поле:

```sql
SELECT DISTINCT owner_name AS struct_name, by_pointer, resolved_final_type_name
FROM v_type_uses
WHERE run_id = :run_id
  AND type_name = :type_name
  AND use_context = 'field'
ORDER BY struct_name;
```

Примечания по охвату:
- Текущая версия `extract_types` не включает локальные переменные в `v_type_uses`.
- При нескольких декларациях одного поля в одной строке (`tcb_t *head, *end;`) создаётся одна запись (первый декларатор); детали — в `raw_context`.

---

*Обновляй этот файл при изменении схемы (`src/db/schema.py`).*
