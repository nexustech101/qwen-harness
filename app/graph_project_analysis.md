=================================================================
TOOL DESCRIPTIONS  (injected into agent system prompt)
=================================================================
## Context Window Manager call Tool Reference

                You have access to a ContextWindowManager that serves as your external project memory.
                DO NOT store file contents in your own context window. Use these tools instead.

                ### Rules
                1. Always call `skeleton()` first. It costs ~1 token/file and orients you.
                2. Use `query()` with the DSL below to load only what you need.
                3. Check `budget_summary()` before loading large files.
                4. Call `evict()` or `evict_lru()` when you no longer need a file.
                5. Call `prompt_context()` to render loaded files as a single string.

                ### Query DSL

                | Pattern              | Meaning                                      |
                |----------------------|----------------------------------------------|
                | app/services/*.py    | Glob on file path                            |
                | re:.*service.*\.py  | Regex on file path                           |
                | tag:security         | Files tagged "security"                      |
                | dep:models/user.py   | Files that import models/user.py             |
                | uses:app/main.py     | Files that app/main.py imports               |
                | rank:10              | Top-10 files by architectural importance     |
                | search:class Repo    | Files whose content matches the pattern      |
                | depth:app/api:2      | Files in app/api/ up to 2 levels deep        |

                Combinators: `&` (AND)  `|` (OR)  `!` (exclude)
                Examples:
                "app/**/*.py & tag:security"
                "dep:models/user.py | rank:5"
                "app/**/*.py ! tests/"

=================================================================
STEP 1 call skeleton()   (~free)
=================================================================
app/
Γö£ΓöÇΓöÇ api/
Γö£ΓöÇΓöÇ core/
Γö£ΓöÇΓöÇ models/
Γö£ΓöÇΓöÇ repositories/
Γö£ΓöÇΓöÇ services/
Γö£ΓöÇΓöÇ __init__.py
ΓööΓöÇΓöÇ main.py

=================================================================
STEP 2 call architecture_report()   (master prompt context)
=================================================================
## Project Architecture Report
Files: 24  |  Dirs: 8  |  Est. tokens (full project): 534

### Top files by import importance (PageRank)
  ARCHITECTURE.md                                     score=0.0417
  CLAUDE.md                                           score=0.0417
  README.md                                           score=0.0417
  app\main.py                                         score=0.0417
  app\__init__.py                                     score=0.0417
  app\api\router.py                                   score=0.0417
  app\api\__init__.py                                 score=0.0417
  app\api\routes\auth.py                              score=0.0417

=================================================================
STEP 3 call query() examples
=================================================================

  Glob call all service files
  query('app/services/*.py')
    app\services\__init__.py
    app\services\auth_service.py
    app\services\invoice_service.py
    app\services\user_service.py

  Tag filter call route files
  query('tag:route')
    app\api\routes\__init__.py
    app\api\routes\auth.py
    app\api\routes\invoices.py
    app\api\routes\users.py

  Regex call anything with 'auth'
  query('re:.*auth.*\\.py')
    app\api\routes\auth.py
    app\services\auth_service.py

  AND combinator
  query('app/**/*.py & tag:security')
    app\core\security.py

  OR combinator
  query('tag:route | tag:security')
    app\core\security.py
    app\api\routes\__init__.py
    app\api\routes\auth.py
    app\api\routes\invoices.py
    app\api\routes\users.py

  Exclude combinator
  query('app/**/*.py ! app/repositories/**')
    app\api\__init__.py
    app\api\router.py
    app\api\routes\__init__.py
    app\api\routes\auth.py
    app\api\routes\invoices.py
    app\api\routes\users.py
    app\core\__init__.py
    app\core\security.py
    app\core\settings.py
    app\models\__init__.py
    app\models\invoice.py
    app\models\user.py
    app\services\__init__.py
    app\services\auth_service.py
    app\services\invoice_service.py
    app\services\user_service.py

  Reverse deps of User model
  query('dep:app/models/user.py')

  Top-5 by importance
  query('rank:5')
    ARCHITECTURE.md
    CLAUDE.md
    README.md
    app\main.py
    app\__init__.py

  Content search
  query('search:class.*Service')
    app\services\auth_service.py
    app\services\invoice_service.py
    app\services\user_service.py

  Subtree with depth limit
  query('depth:app/api:2')

=================================================================
STEP 4 call Targeted load with budget tracking
=================================================================

Loaded top-5 important files:
  ARCHITECTURE.md  (18 tok, importance=0.0417)
  CLAUDE.md  (34 tok, importance=0.0417)
  README.md  (15 tok, importance=0.0417)
  app\main.py  (37 tok, importance=0.0417)
  app\__init__.py  (1 tok, importance=0.0417)

Token budget    : 1,200
Tokens used     : 105
Tokens free     : 1,095
Files loaded    : 5
Loaded files:
  ARCHITECTURE.md                                        18 tok  importance=0.0417
  CLAUDE.md                                              34 tok  importance=0.0417
  README.md                                              15 tok  importance=0.0417
  app\main.py                                            37 tok  importance=0.0417
  app\__init__.py                                         1 tok  importance=0.0417

=================================================================
STEP 5 call prompt_context()   (what the LLM receives)
=================================================================
### ARCHITECTURE.md   [tokens: 18]
# Architecture
Layered: routes call services call repositories call models


### CLAUDE.md   [tokens: 34]
# Agent Instructions
Focus on app/. Tests live in tests/.
Never store full file contents in context ├óΓé¼ΓÇ¥ use the ContextWindowManager.


### README.md   [tokens: 15]
# Demo Project
A FastAPI service with users and invoices.


### app\main.py   [tokens: 37]
from fastapi import FastAPI
from app.api.router import router
from app.core.settings import Settings
app = FastAPI()
app.include_router(router)


### app\__init__.py   [tokens: 1]
<content not loaded>

=================================================================
STEP 6 call evict_lru()   (free 100 tokens)
=================================================================
Evicted: ['ARCHITECTURE.md', 'CLAUDE.md', 'README.md', 'app\\main.py']

Token budget    : 1,200
Tokens used     : 1
Tokens free     : 1,199
Files loaded    : 1
Loaded files:
  app\__init__.py                                         1 tok  importance=0.0417
