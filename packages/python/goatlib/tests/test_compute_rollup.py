from goatlib.tasks.compute_rollup import select_chargeable, tool_from_path


def _job(**o):
    base = {
        "job_id": "j1",
        "user_id": "u1",
        "runnable_path": "f/goat/tools/buffer",
        "trigger_kind": None,
        "status": "success",
        "duration_ms": 4000,
        "has_children": False,
        "parent_job": None,
        "args": {},
    }
    base.update(o)
    return base


def test_tool_from_path():
    assert tool_from_path("f/goat/tools/catchment_area_pt") == "catchment_area_pt"
    assert tool_from_path(None) == "(unknown)"


def test_charges_a_standalone_tool():
    items = select_chargeable([_job()], already_charged=set())
    assert len(items) == 1
    it = items[0]
    assert it.user_id == "u1"
    assert it.action == "buffer"
    assert it.duration_seconds == 4.0  # 4000 ms
    assert it.payload["job_id"] == "j1"


def test_excludes_scheduled_failed_orchestrator_and_already_charged():
    jobs = [
        _job(job_id="sched", trigger_kind="schedule"),
        _job(job_id="fail", status="failure"),
        _job(job_id="orch", has_children=True),  # workflow_runner parent
        _job(job_id="orch2", runnable_path="f/goat/tools/workflow_runner"),
        _job(job_id="dup"),  # already charged
        _job(job_id="ok"),
    ]
    items = select_chargeable(jobs, already_charged={"dup"})
    assert {i.job_id for i in items} == {"ok"}


def test_workflow_node_tags_run_workflow_node_and_project():
    job = _job(
        job_id="node1",
        runnable_path="f/goat/tools/oev_gueteklassen",
        parent_job="orch-job-7",
        args={
            "user_id": "u1",
            "workflow_id": "wf9",
            "node_id": "n3",
            "project_id": "p7",
        },
    )
    p = select_chargeable([job], already_charged=set())[0].payload
    assert p["workflow_id"] == "wf9"
    assert p["node_id"] == "n3"
    assert (
        p["workflow_run_id"] == "orch-job-7"
    )  # parent_job = per-execution id (counts runs)
    assert p["project_id"] == "p7"


def test_skips_job_without_user():
    assert select_chargeable([_job(user_id=None)], set()) == []


def test_housekeeping_jobs_are_free():
    from goatlib.tasks.compute_rollup import select_chargeable

    job = {
        "job_id": "j1",
        "user_id": "u1",
        "args": {},
        "runnable_path": "f/goat/tools/layer_delete",
        "trigger_kind": None,
        "status": "success",
        "has_children": False,
        "duration_ms": 4000,
    }
    assert select_chargeable([job], set()) == []
    assert (
        len(select_chargeable([{**job, "runnable_path": "f/goat/tools/buffer"}], set()))
        == 1
    )


def test_an_export_carries_its_file_size_for_data_transfer():
    layer = _job(runnable_path="f/goat/tools/layer_export", export_size="6746")
    project = _job(
        job_id="p1", runnable_path="f/goat/tools/project_export", export_size="42989205"
    )
    items = select_chargeable([layer, project], set())
    assert [i.export_bytes for i in items] == [6746, 42989205]


def test_other_tools_and_odd_sizes_carry_no_data_transfer():
    other = _job(export_size="999")  # not an export: ignored even with a size
    broken = _job(
        job_id="b1", runnable_path="f/goat/tools/layer_export", export_size="n/a"
    )
    missing = _job(job_id="m1", runnable_path="f/goat/tools/layer_export")
    assert [
        i.export_bytes for i in select_chargeable([other, broken, missing], set())
    ] == [0, 0, 0]
