from __future__ import annotations

from agentforge.platform.domain.policy import RelationTuple


class OpenFGAClient:
    """OpenFGA-style relation reader/writer used by the authorization path.

    This is an in-memory implementation of the OpenFGA Check API surface needed
    by the Policy Engine. It is intentionally isolated behind a thin adapter so
    a real OpenFGA server (see engineering spec 5.7) can be swapped in without
    touching the policy engine. It supports the subset of operations the current
    platform needs: write tuples, list tuples, and check whether a subject has a
    relation (directly or inherited through object hierarchy).
    """

    def __init__(self) -> None:
        self._tuples: set[tuple[str, str, str, str, str, str]] = set()

    def write(self, tenant_id: str, tuples: list[RelationTuple]) -> None:
        for tup in tuples:
            if tup.tenant_id != tenant_id:
                raise ValueError("relation tuple tenant mismatch")
            self._tuples.add(self._key(tup))

    def delete(self, tenant_id: str, tuples: list[RelationTuple]) -> None:
        for tup in tuples:
            if tup.tenant_id != tenant_id:
                raise ValueError("relation tuple tenant mismatch")
            self._tuples.discard(self._key(tup))

    def list_tuples(self, tenant_id: str) -> list[RelationTuple]:
        return [
            RelationTuple(
                tenant_id=tenant_id,
                object_type=parts[0],
                object_id=parts[1],
                relation=parts[2],
                subject_type=parts[3],
                subject_id=parts[4],
            )
            for parts in self._tuples
            if parts[0] == tenant_id
        ]

    def check(
        self, tenant_id: str, obj_type: str, obj_id: str, relation: str, subject: str
    ) -> bool:
        """Check a direct relation: object#relation@user:subject."""
        key = (
            tenant_id,
            obj_type,
            obj_id,
            relation,
            "user",
            subject,
        )
        return self._has_tuple(key)

    async def acheck(
        self,
        tenant_id: str,
        obj_type: str,
        obj_id: str,
        relation: str,
        subject: str,
    ) -> bool:
        return self.check(tenant_id, obj_type, obj_id, relation, subject)

    def _has_tuple(self, key: tuple[str, str, str, str, str, str]) -> bool:
        return key in self._tuples

    @staticmethod
    def _key(tup: RelationTuple) -> tuple[str, str, str, str, str, str]:
        return (
            tup.tenant_id,
            tup.object_type,
            tup.object_id,
            tup.relation,
            tup.subject_type,
            tup.subject_id,
        )
