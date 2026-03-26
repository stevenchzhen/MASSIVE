from cell.runtime.sampling import derive_task_data_samples, should_derive_task_data_samples
from cell.types import Blocker, BlockerCategory, Document, TaskInput


def test_derive_task_data_samples_prefers_blocker_relevant_content() -> None:
    task = TaskInput(
        task_id="task-1",
        instruction="parse proprietary rows",
        input_documents=[
            Document(
                name="invoice.txt",
                content="HEADER<<x>>\nROW<<name=Rotor Kit;qty=2;unit_usd=12.50>>\nTOTAL<<usd=33.25>>\n",
                content_hash="hash-doc",
            )
        ],
        input_data={"records": [{"kind": "row", "raw": "ROW<<name=Seal Pack;qty=1;unit_usd=7.00>>"}]},
        result_schema={"type": "object"},
    )
    blocker = Blocker(
        category=BlockerCategory.MISSING_CAPABILITY,
        description="Need a parser for ROW<<...>> segments",
        attempted_approaches=["manual review"],
        what_would_unblock="A parser for ROW<<...>> lines",
        input_sample="ROW<<name=Rotor Kit;qty=2;unit_usd=12.50>>",
        confidence_in_diagnosis=0.9,
    )

    samples = derive_task_data_samples(task, blocker, sample_ratio=0.5, max_samples=3)

    assert samples
    assert any("ROW<<" in sample.content for sample in samples)
    assert all(sample.source_id in {"input_data", task.input_documents[0].document_id} for sample in samples)


def test_should_derive_task_data_samples_for_data_shape_dependent_blocker() -> None:
    task = TaskInput(
        task_id="task-1",
        instruction="parse rows",
        input_documents=[
            Document(
                name="invoice.txt",
                content="ROW<<name=Rotor Kit;qty=2;unit_usd=12.50>>",
                content_hash="hash-doc",
            )
        ],
        result_schema={"type": "object"},
    )
    blocker = Blocker(
        category=BlockerCategory.MISSING_CAPABILITY,
        description="Need a parser for custom ROW segments",
        attempted_approaches=["manual review"],
        what_would_unblock="A parser for the proprietary format",
        input_sample="ROW<<name=Rotor Kit;qty=2;unit_usd=12.50>>",
        confidence_in_diagnosis=0.9,
    )

    assert should_derive_task_data_samples(task, blocker) is True


def test_should_not_derive_task_data_samples_for_generic_helper_tool() -> None:
    task = TaskInput(
        task_id="task-1",
        instruction="sum numbers",
        input_data={"a": 2, "b": 3},
        result_schema={"type": "object"},
    )
    blocker = Blocker(
        category=BlockerCategory.MISSING_CAPABILITY,
        description="Need an arithmetic helper to add two numbers",
        attempted_approaches=["mental math disabled"],
        what_would_unblock="An adder tool",
        input_sample=None,
        confidence_in_diagnosis=0.9,
    )

    assert should_derive_task_data_samples(task, blocker) is False
