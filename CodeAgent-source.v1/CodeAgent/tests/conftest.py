import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

SAMPLE_DOC = """\
Analysis Plan:
Scope: demo.

# A. Executive Summary
The demo system does things.

# B. Traceability & Rationale

| Requirement ID | Short Text | Diagram(s) | Component(s) | Artifact filename(s) | Rationale |
| --- | --- | --- | --- | --- | --- |
| FR-1 | Play game | UseCaseDiagram | GameComponent | openapi.yaml | Allows play |
| NFR-1 | Performance | SequenceDiagram1 | GameComponent | internal.proto | Fast |
| ASR-1 | Data durability | DeploymentDiagram | QuestionComponent | sql/question_ddl.sql | Durable |

# D. Detailed Technical Design

```yml
openapi: 3.0.0
info:
  title: Demo API
```

```sql
CREATE TABLE games (id SERIAL PRIMARY KEY);
```
"""

SAMPLE_VIEW = """\
## ScenarioView
1. UseCase — Scenario View: Use Case Diagram
```plantuml
@startuml UseCaseDiagram
actor EndUser as "End User"
usecase "Play Game" as (PlayGame)
EndUser -- (PlayGame)
@enduml
```

## LogicView
2. Class — Logic View: Class Diagram
```plantuml
@startuml ClassDiagram
class Game {
  - id: string
  - score: int
  + play(): void
}
class Question {
  - prompt: string
}
Game --* Question
@enduml
```

## ProcessView
6. Sequence — Process View: Sequence Diagram
```plantuml
@startuml SequenceDiagram1
participant User
participant Game
User->>Game: play()
@enduml
```
"""


@pytest.fixture
def sample_inputs(tmp_path):
    doc = tmp_path / "Architecture_Documentation.md"
    view = tmp_path / "Architecture_View.md"
    doc.write_text(SAMPLE_DOC, encoding="utf-8")
    view.write_text(SAMPLE_VIEW, encoding="utf-8")
    return doc, view
