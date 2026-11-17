from fastapi import HTTPException

from app.models import Invite, InviteChannel
from app.repositories.bill_repo import BillRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.user_repo import UserRepository
from app.schemas.invite_schemas import InviteResolved, InviteResponse
from app.utils.telegram import mini_app_link

INVITE_PARAM_PREFIX = "inv_"


def invite_start_param(code: str) -> str:
    return f"{INVITE_PARAM_PREFIX}{code}"


class InviteService:
    """Mints and resolves the codes that carry attribution through a deep link."""

    def __init__(
        self,
        invite_repo: InviteRepository,
        bill_repo: BillRepository,
        user_repo: UserRepository,
    ):
        self.invite_repo = invite_repo
        self.bill_repo = bill_repo
        self.user_repo = user_repo

    def create(
        self,
        bill_id: int,
        inviter_user_id: int,
        channel: InviteChannel,
        seat_participant_id: int | None = None,
    ) -> Invite:
        bill = self.bill_repo.get_by_id(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")

        is_member = (
            bill.owner_id == inviter_user_id
            or self.bill_repo.get_participant_by_bill_and_user(bill_id, inviter_user_id)
            is not None
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="Not authorized to share this bill")

        if seat_participant_id is not None:
            if bill.owner_id != inviter_user_id:
                raise HTTPException(
                    status_code=403, detail="Only the owner can invite to a specific seat"
                )
            seat = self.bill_repo.get_participant_by_id(seat_participant_id)
            if not seat or seat.bill_id != bill_id:
                raise HTTPException(
                    status_code=404, detail="Participant not found for this bill"
                )

        return self.invite_repo.create(
            Invite(
                bill_id=bill_id,
                inviter_user_id=inviter_user_id,
                seat_participant_id=seat_participant_id,
                channel=channel,
            )
        )

    def create_response(
        self,
        bill_id: int,
        inviter_user_id: int,
        channel: InviteChannel,
        seat_participant_id: int | None = None,
    ) -> InviteResponse:
        invite = self.create(bill_id, inviter_user_id, channel, seat_participant_id)
        return InviteResponse(
            code=invite.code,
            channel=invite.channel,
            deep_link=mini_app_link(invite_start_param(invite.code)),
        )

    def resolve(self, code: str) -> InviteResolved:
        invite = self.invite_repo.get_by_code(code)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found")
        bill = self.bill_repo.get_by_id(invite.bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        inviter = self.user_repo.get_by_id(invite.inviter_user_id)
        return InviteResolved(
            code=invite.code,
            channel=invite.channel,
            bill_id=bill.id,
            public_token=bill.public_token,
            seat_participant_id=invite.seat_participant_id,
            inviter_user_id=invite.inviter_user_id,
            inviter_name=inviter.name if inviter else None,
        )

    def inviter_for(self, code: str | None, bill_id: int) -> int | None:
        """The inviter an incoming code stands for, ignoring codes for other bills."""
        if not code:
            return None
        invite = self.invite_repo.get_by_code(code)
        if not invite or invite.bill_id != bill_id:
            return None
        return invite.inviter_user_id
