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
10. [conditional_regions](#10-conditional_regions)
11. [preprocessor_symbols](#11-preprocessor_symbols)
12. [entity_presence_conditions](#12-entity_presence_conditions)
13. [Поля трассировки — общий глоссарий](#13-поля-трассировки--общий-глоссарий)
14. [Значения confidence](#14-значения-confidence)
15. [Значения detector](#15-значения-detector)

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

## 10. `conditional_regions`

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

## 11. `preprocessor_symbols`

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

## 12. `entity_presence_conditions`

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

## 13. Поля трассировки — общий глоссарий

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

## 14. Значения `confidence`

| Значение | Интерпретация |
|----------|---------------|
| `HIGH`   | Несколько надёжных детекторов согласны, или ctags+tree_sitter в паре. Можно цитировать без оговорок. |
| `MEDIUM` | Один надёжный детектор (`ctags` в одиночку, `cscope`). Требует оговорки об источнике. |
| `LOW`    | Только эвристика (`regex`, `manual_rule`) или один слабый детектор. Обязательна пометка «требует верификации». |

**Правило повышения:** `confidence` не может подняться выше `MEDIUM`, если
в группе присутствуют только `cscope` и `regex` (нет `ctags` или `tree_sitter`).

---

## 15. Значения `detector`

| Значение      | Инструмент           | Надёжность | Стадия              |
|---------------|----------------------|------------|---------------------|
| `ctags`       | universal-ctags      | Высокая    | extract_entities    |
| `tree_sitter` | tree-sitter-c        | Высокая    | (planned)           |
| `cscope`      | cscope               | Средняя    | extract_usages      |
| `regex`       | Python `re`          | Низкая     | все стадии          |
| `manual_rule` | ручное правило       | Переменная | reconcile           |

---

*Обновляй этот файл при изменении схемы (`src/db/schema.py`).*
