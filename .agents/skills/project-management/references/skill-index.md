# Индекс навыков

Этот файл служит навигацией по переносимым навыкам каркаса.

## Правило применения

Индекс помогает выбрать навык, но не заменяет сам навык. Если задача совпадает с
назначением навыка из списка, агент обязан открыть соответствующий
`<skill>/SKILL.md` из текущего корня навыков и применить его правила до
исполнения.

Для запросов вида «Настрой проект», «Перенастрой проект», «Начни новый проект»,
«Инициализируй проект», «Подготовь новый репозиторий» и близких по смыслу
запросов применяй `ait-setup/SKILL.md`.

## Навыки

- `ai-agents-md-maintenance` — роль: `technical-writer` — сопровождение
  `AGENTS.md`. Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-setup-apm` — роль: `cross-role` — настройка и проверка APM-коллекций.
  Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-application-check` — роль: `analyst` — предварительная оценка пригодности
  задачи для ИИ. Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-audit-agents-md` — роль: `technical-writer` — проверка качества
  `AGENTS.md`. Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-audit-project` — роль: `cross-role` — проверка правил и агентских
  инструкций проекта. Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-data-collection` — роль: `analyst` — сбор данных перед изменением правил,
  ролей, навыков, шаблонов или источников истины. Источник:
  `github.com/mekras/ai-agent-supervisor`.
- `ai-rule-failure-analysis` — роль: `analyst` — разбор нарушений правил или
  маршрутизации агентом. Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-skill-development` — роль: `cross-role` — разработка и проверка навыков
  агента. Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-setup-subagents` — роль: `cross-role` — политика экономного использования
  подагентов, выбор моделей, лимиты и эскалации. Источник:
  `github.com/mekras/ai-agent-supervisor`.
- `ai-work-control` — роль: `cross-role` — контроль существенных изменений
  правил, ролей, навыков, шаблонов, документации или источников истины.
  Источник: `github.com/mekras/ai-agent-supervisor`.
- `ai-work-result-evaluation` — роль: `cross-role` — оценка результата ИИ перед
  принятием, публикацией или использованием как основания следующего шага.
  Источник: `github.com/mekras/ai-agent-supervisor`.
- `ait-setup` — роль: `project-manager` — настройка нового или существующего
  проекта под актуальные правила продукта через диалог.
- `analysis` — роль: `analyst` — аналитический разбор.
- `ait-docs-concept` — роль: `technical-writer` — создание и сопровождение
  концепции проекта как главного ориентира проектной документации.
- `documentation-structure-audit` — роль: `technical-writer` — проверка текущей
  структуры документации и безопасные исправления.
- `documentation-structure-design` — роль: `technical-writer` — проектирование
  структуры документации проекта на основании данных и анализа.
- `documentation-structure-rules` — роль: `technical-writer` — фиксация и
  обновление правил, поддерживающих выбранную структуру документации.
- `kc-analysis` — роль: `analyst` — анализ корпуса знаний. Источник:
  `github.com/mekras/project-knowlege-corpus`.
- `kc-impact-audit` — роль: `analyst` — анализ влияния источников на производные
  материалы. Источник: `github.com/mekras/project-knowlege-corpus`.
- `kc-inventory` — роль: `source-inventory` — учёт и техническая синхронизация
  источников. Источник: `github.com/mekras/project-knowlege-corpus`.
- `kc-normalization` — роль: `normalizer` — нормализация первичных данных.
  Источник: `github.com/mekras/project-knowlege-corpus`.
- `kc-pipeline` — роль: `cross-role` — координация конвейера первичных данных.
  Источник: `github.com/mekras/project-knowlege-corpus`.
- `kc-setup` — роль: `source-inventory` — настройка проекта на работу с корпусом
  знаний. Источник: `github.com/mekras/project-knowlege-corpus`.
- `kc-sources-add` — роль: `source-inventory` — техническое добавление нового
  источника в корпус знаний. Источник:
  `github.com/mekras/project-knowlege-corpus`.
- `kc-statements` — роль: `statement-extractor` — извлечение утверждений, фактов
  и наблюдений из источников. Источник:
  `github.com/mekras/project-knowlege-corpus`.
- `kc-status` — роль: `source-inventory` — сводка состояния корпуса знаний.
  Источник: `github.com/mekras/project-knowlege-corpus`.
- `kc-validation` — роль: `source-inventory` — проверка корпуса знаний.
  Источник: `github.com/mekras/project-knowlege-corpus`.
- `private-project-knowledge` — роль: `source-inventory` — приватный локальный
  слой знаний проекта для агента вне VCS.
- `project-management` — роль: `project-manager` — маршрутизация задачи и выбор
  режима.
- `project-readme` — роль: `technical-writer` — сопровождение проектного
  `README.md`.
- `requirements-analysis` — роль: `analyst` — анализ и моделирование требований.
- `requirements-elicitation` — роль: `analyst` — выявление требований и работа с
  заинтересованными лицами.
- `requirements-management` — роль: `analyst` — приоритеты, изменения, статусы и
  связи требований.
- `requirements-specification` — роль: `analyst` — запись требований в
  проверяемом формате.
- `requirements-validation` — роль: `analyst` — проверка и подготовка требований
  к утверждению.
- `software-architecture` — роль: `software-architect` — архитектура ПО, ADR,
  компонентные границы и управление сложностью системы.
- `technical-writing` — роль: `technical-writer` — техническое письмо.
- `transcript-analysis` — роль: `technical-writer` — разбор и очистка
  стенограмм. Источник: `github.com/mekras/project-knowlege-corpus`.

## Правило размещения

Каждый навык хранится в собственном каталоге рядом с `references/`, `assets/` и
`evals/`, если они нужны этому навыку.
