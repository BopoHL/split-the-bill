from typing import Literal, Optional
from sqlmodel import Session, select, or_, func
from sqlalchemy import select as sa_select, union
from sqlalchemy.orm import aliased, selectinload
from app.models import Bill, BillItem, BillUser, BillStatus, User

StatusFilter = Optional[Literal["active", "closed"]]
RoleFilter = Optional[Literal["owner", "participant"]]


class BillRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, bill: Bill) -> Bill:
        self.session.add(bill)
        self.session.commit()
        self.session.refresh(bill)
        return bill

    def get_by_id(self, bill_id: int) -> Bill | None:
        """A soft-deleted bill is gone as far as the app is concerned."""
        bill = self.session.get(Bill, bill_id)
        return None if bill is None or bill.deleted_at is not None else bill

    def get_by_id_for_update(self, bill_id: int) -> Bill | None:
        """Lock a live bill for an atomic money/allocation mutation.

        Read again from the row the lock holds: the copy loaded earlier in the
        request (by the owner check, say) may say «open» about a bill another
        request has closed since."""
        statement = (
            select(Bill)
            .where(Bill.id == bill_id, Bill.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.exec(statement).first()

    def get_by_id_including_deleted(self, bill_id: int) -> Bill | None:
        """Deleted rows are still reachable for the admin panel and for restore."""
        return self.session.get(Bill, bill_id)

    def get_by_token(self, token: str) -> Bill | None:
        statement = select(Bill).where(
            Bill.public_token == token, Bill.deleted_at.is_(None)
        )
        return self.session.exec(statement).first()

    def get_user_bills(
        self,
        user_id: int,
        offset: int = 0,
        limit: int = 10,
        status_filter: StatusFilter = None,
        query: str | None = None,
        role: RoleFilter = None,
    ) -> list[tuple[Bill, int, int, int, int, int]]:
        """Return bills the user owns or participates in, newest first.

        Each row is (Bill, participants_count, items_count, paid_count,
        payers_count, payers_paid) — the counts come from correlated subqueries
        so the whole page is one query (no N+1).

        `payers_*` exclude the owner: the dashboard counter answers "how many of
        the people who owe me have paid", and the owner is never one of them.

        status_filter:
          - "active":  not BillStatus.CLOSED (open/paid)
          - "closed":  BillStatus.CLOSED
          - None:      no status filtering

        query narrows to bills whose title, owner or anyone at the table
        matches; role to the ones the user owns or only joined.
        """
        from sqlmodel import and_

        # Correlated subqueries, evaluated once per Bill row.
        count_stmt = (
            sa_select(func.count(BillUser.id))
            .where(BillUser.bill_id == Bill.id)
            .correlate(Bill)
            .scalar_subquery()
        )
        items_count_stmt = (
            sa_select(func.count(BillItem.id))
            .where(BillItem.bill_id == Bill.id)
            .correlate(Bill)
            .scalar_subquery()
        )
        paid_count_stmt = (
            sa_select(func.count(BillUser.id))
            .where(and_(BillUser.bill_id == Bill.id, BillUser.is_paid.is_(True)))
            .correlate(Bill)
            .scalar_subquery()
        )
        payers_count_stmt = (
            sa_select(func.count(BillUser.id))
            .where(
                and_(
                    BillUser.bill_id == Bill.id,
                    BillUser.allocated_amount > 0,
                    or_(BillUser.user_id.is_(None), BillUser.user_id != Bill.owner_id),
                )
            )
            .correlate(Bill)
            .scalar_subquery()
        )
        payers_paid_stmt = (
            sa_select(func.count(BillUser.id))
            .where(
                and_(
                    BillUser.bill_id == Bill.id,
                    BillUser.is_paid.is_(True),
                    BillUser.allocated_amount > 0,
                    or_(BillUser.user_id.is_(None), BillUser.user_id != Bill.owner_id),
                )
            )
            .correlate(Bill)
            .scalar_subquery()
        )

        statement = (
            select(
                Bill,
                count_stmt.label("participants_count"),
                items_count_stmt.label("items_count"),
                paid_count_stmt.label("paid_count"),
                payers_count_stmt.label("payers_count"),
                payers_paid_stmt.label("payers_paid"),
            )
            .where(*self.user_bill_conditions(user_id, status_filter, query, role))
            .order_by(Bill.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def count_user_bills(
        self,
        user_id: int,
        status_filter: StatusFilter = None,
        query: str | None = None,
    ) -> tuple[int, int]:
        """How many bills the list holds, and how many of them the user owns —
        in one pass."""
        statement = sa_select(func.count(Bill.id), func.count(Bill.id).filter(Bill.owner_id == user_id)).where(
            *self.user_bill_conditions(user_id, status_filter, query, None)
        )
        return tuple(self.session.exec(statement).one())

    @staticmethod
    def user_bill_conditions(
        user_id: int,
        status_filter: StatusFilter,
        query: str | None,
        role: RoleFilter,
    ) -> list:
        """The user's bills — owned, or with a seat at the table.

        Said as «the id is one of these», gathered from the two indexes, rather
        than an owner-or-seated test on every bill: that one makes Postgres
        read every bill there is, and the cost it guesses turns on its JIT,
        which alone takes longer than the query.
        """
        mine = union(
            sa_select(Bill.id).where(Bill.owner_id == user_id),
            sa_select(BillUser.bill_id).where(BillUser.user_id == user_id),
        )
        conditions = [
            Bill.deleted_at.is_(None),
            Bill.is_demo.is_(False),
            Bill.id.in_(mine),
        ]
        if status_filter == "active":
            conditions.append(Bill.status != BillStatus.CLOSED)
        elif status_filter == "closed":
            conditions.append(Bill.status == BillStatus.CLOSED)
        if role == "owner":
            conditions.append(Bill.owner_id == user_id)
        elif role == "participant":
            conditions.append(Bill.owner_id != user_id)
        # «@alice» is how people write a username; the @ is not part of it.
        needle = (query or "").strip().lstrip("@").lower()
        if needle:

            def matches(column):
                return func.lower(column).contains(needle, autoescape=True)

            people = sa_select(User.id).where(
                or_(matches(User.name), matches(User.surname), matches(User.username))
            )
            # Only the user's own tables are searched for who sat at them.
            at_the_table = sa_select(BillUser.bill_id).where(
                BillUser.bill_id.in_(mine),
                or_(matches(BillUser.guest_name), BillUser.user_id.in_(people)),
            )
            conditions.append(or_(matches(Bill.title), Bill.owner_id.in_(people), Bill.id.in_(at_the_table)))
        return conditions

    def get_seats_by_bill(self, bill_ids: list[int]) -> dict[int, list[BillUser]]:
        """Each bill's seats in table order, in one query."""
        seats: dict[int, list[BillUser]] = {}
        if not bill_ids:
            return seats
        statement = select(BillUser).where(BillUser.bill_id.in_(bill_ids)).order_by(BillUser.seat_index)
        for seat in self.session.exec(statement).all():
            seats.setdefault(seat.bill_id, []).append(seat)
        return seats

    def have_met(self, user_id: int, other_id: int) -> bool:
        """Whether the two shared a bill, or the first brought the second in —
        get_acquaintances' two ways, asked of one person."""
        mine, theirs = aliased(BillUser), aliased(BillUser)
        shared = self.session.exec(
            select(mine.id)
            .join(theirs, theirs.bill_id == mine.bill_id)
            .join(Bill, Bill.id == mine.bill_id)
            .where(mine.user_id == user_id, theirs.user_id == other_id, Bill.deleted_at.is_(None))
            .limit(1)
        ).first()
        if shared is not None:
            return True
        other = self.session.get(User, other_id)
        return other is not None and other.invited_by_user_id == user_id

    def get_acquaintances(self, user_id: int, limit: int) -> list[User]:
        """People this user has actually met in the app, most recent first.

        Two ways to have met: sharing a bill, or having been brought into the
        app by them. The second is not covered by the first — an invite that was
        opened but whose seat was never taken leaves an account and no shared
        bill.
        """
        mine = aliased(BillUser)
        theirs = aliased(BillUser)
        together = (
            sa_select(
                theirs.user_id.label("user_id"),
                func.max(Bill.created_at).label("last_seen"),
            )
            .join(mine, mine.bill_id == theirs.bill_id)
            .join(Bill, Bill.id == theirs.bill_id)
            .where(
                mine.user_id == user_id,
                theirs.user_id.is_not(None),
                theirs.user_id != user_id,
                Bill.deleted_at.is_(None),
            )
            .group_by(theirs.user_id)
        )
        brought_in = sa_select(
            User.id.label("user_id"), User.created_at.label("last_seen")
        ).where(User.invited_by_user_id == user_id, User.id != user_id)

        met = together.union_all(brought_in).subquery()
        statement = (
            sa_select(User, func.max(met.c.last_seen).label("last_seen"))
            .join(met, met.c.user_id == User.id)
            .group_by(User.id)
            .order_by(func.max(met.c.last_seen).desc(), User.id.desc())
            .limit(limit)
        )
        return [user for user, _ in self.session.exec(statement).all()]

    def search_users_by_username(self, term: str, limit: int) -> list[User]:
        """Username lookup for assigning someone who isn't an acquaintance yet.

        A prefix rather than a substring, and never on an empty term: this reads
        strangers' accounts, so it answers «who is @kolya» and not «show me
        everyone with an o in their name». The term is escaped, so a «%» or
        «_» typed into the box matches those characters and not everyone.
        """
        needle = term.strip().lstrip("@").lower()
        if not needle:
            return []
        statement = (
            select(User)
            .where(func.lower(User.username).startswith(needle, autoescape=True))
            .order_by(func.length(User.username), User.id)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def get_participants_for_bills(
        self, bill_ids: list[int]
    ) -> list[tuple[int, str | None, str | None, str | None, str | None]]:
        """Participant rows for a set of bills, ordered for a stable preview.

        Returns (bill_id, guest_name, name, username, avatar_url) tuples; the
        caller groups by bill_id and caps the preview length. One query for the
        whole page — no N+1.
        """
        if not bill_ids:
            return []
        statement = (
            sa_select(
                BillUser.bill_id,
                BillUser.guest_name,
                User.name,
                User.username,
                User.avatar_url,
            )
            .join(User, User.id == BillUser.user_id, isouter=True)
            .where(BillUser.bill_id.in_(bill_ids))
            .order_by(BillUser.bill_id, BillUser.id)
        )
        return self.session.exec(statement).all()

    def add_item(self, item: BillItem) -> BillItem:
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def add_participant(self, participant: BillUser) -> BillUser:
        self.session.add(participant)
        self.session.commit()
        self.session.refresh(participant)
        return participant

    def get_items_by_bill_id(self, bill_id: int) -> list[BillItem]:
        statement = select(BillItem).where(BillItem.bill_id == bill_id).options(selectinload(BillItem.assignments))
        return self.session.exec(statement).all()

    def get_participants_by_bill_id(self, bill_id: int) -> list[BillUser]:
        """Seats in table order.

        Without the ORDER BY the order is whatever the planner returns, and
        Postgres moves an updated row to the end of the heap — so claiming or
        freeing a seat reshuffled the participant list in the UI.
        """
        statement = (
            select(BillUser)
            .where(BillUser.bill_id == bill_id)
            .order_by(BillUser.seat_index)
            .options(selectinload(BillUser.user))
        )
        return self.session.exec(statement).all()

    def get_participant_by_id(self, participant_id: int) -> BillUser | None:
        return self.session.get(BillUser, participant_id)

    def get_item_by_id(self, item_id: int) -> BillItem | None:
        return self.session.get(BillItem, item_id)

    def get_item_by_id_for_update(self, item_id: int) -> BillItem | None:
        statement = (
            select(BillItem)
            .where(BillItem.id == item_id)
            .options(selectinload(BillItem.assignments))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.exec(statement).first()

    def delete_item(self, item: BillItem):
        self.session.delete(item)
        self.session.commit()

    def delete_participant(self, participant: BillUser):
        self.session.delete(participant)
        self.session.commit()

    def get_participant_by_bill_and_user(self, bill_id: int, user_id: int) -> BillUser | None:
        statement = select(BillUser).where(BillUser.bill_id == bill_id, BillUser.user_id == user_id).options(selectinload(BillUser.user))
        return self.session.exec(statement).first()
