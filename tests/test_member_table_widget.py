from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from app.viewmodels.members_state import MemberSummary
from app.views.tabs.members.member_table_widget import MemberTableWidget


def _member(
    member_id: int,
    name: str,
    status: str = "active",
) -> MemberSummary:
    return MemberSummary.from_member(
        {
            "id": member_id,
            "full_name": name,
            "email": f"{member_id}@example.com",
            "phone_number": str(member_id),
            "active_membership": {"status": status},
        }
    )


def _table(qtbot) -> MemberTableWidget:
    table = MemberTableWidget()
    table.resize(600, 300)
    qtbot.addWidget(table)
    table.show()
    table.populate(
        [
            _member(101, "Zoe", "inactive"),
            _member(202, "Ana", "active"),
            _member(303, "Luis", "expired"),
        ]
    )
    return table


def _visible_member_id(table: MemberTableWidget, row: int) -> int:
    return table.item(row, 0).data(Qt.ItemDataRole.UserRole)


def _assert_visible_rows_resolve_to_their_own_summary(
    table: MemberTableWidget,
) -> None:
    for row in range(table.rowCount()):
        expected_id = _visible_member_id(table, row)
        table.selectRow(row)
        summary = table.current_summary()
        assert summary is not None
        assert summary.member_id == expected_id
        assert summary.full_name == table.item(row, 0).text()


@pytest.mark.parametrize(
    ("column", "order"),
    [
        (0, Qt.SortOrder.AscendingOrder),
        (0, Qt.SortOrder.DescendingOrder),
        (1, Qt.SortOrder.AscendingOrder),
        (1, Qt.SortOrder.DescendingOrder),
    ],
)
def test_selection_emits_the_visible_member_after_sorting(qtbot, column, order):
    table = _table(qtbot)
    emitted = []
    table.selection_changed.connect(emitted.append)

    table.sortItems(column, order)

    for row in range(table.rowCount()):
        expected_id = _visible_member_id(table, row)
        item_rect = table.visualItemRect(table.item(row, 0))
        qtbot.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=item_rect.center(),
        )

        assert emitted
        assert emitted[-1] is not None
        assert emitted[-1].member_id == expected_id
        assert table.current_summary().member_id == expected_id


def test_select_member_finds_the_visual_row_after_sorted_refresh(qtbot):
    table = _table(qtbot)
    table.sortItems(0, Qt.SortOrder.AscendingOrder)

    table.populate(
        [
            _member(404, "Carlos"),
            _member(505, "Beto"),
            _member(606, "Adriana"),
        ]
    )

    assert [table.item(row, 0).text() for row in range(table.rowCount())] == [
        "Adriana",
        "Beto",
        "Carlos",
    ]
    assert table.select_member(404) is True
    assert _visible_member_id(table, table.currentRow()) == 404
    assert table.current_summary().member_id == 404
    _assert_visible_rows_resolve_to_their_own_summary(table)


def test_upsert_and_remove_target_member_identity_while_sorted(qtbot):
    table = _table(qtbot)
    table.sortItems(0, Qt.SortOrder.AscendingOrder)

    table.upsert_member(_member(101, "Aaron", "active"))
    table.upsert_member(_member(404, "Beto", "expired"))

    visible_ids = {
        _visible_member_id(table, row) for row in range(table.rowCount())
    }
    assert visible_ids == {101, 202, 303, 404}
    assert table.item(0, 0).text() == "Aaron"
    _assert_visible_rows_resolve_to_their_own_summary(table)

    table.remove_member(303)

    visible_ids = {
        _visible_member_id(table, row) for row in range(table.rowCount())
    }
    assert visible_ids == {101, 202, 404}
    assert {summary.member_id for summary in table.summaries()} == visible_ids
    _assert_visible_rows_resolve_to_their_own_summary(table)
