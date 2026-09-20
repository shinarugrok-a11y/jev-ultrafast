"""Repository domain. Screens changes and estimates risk; never applies them."""

from jev_ultrafast.core.action_space import ActionSpace, LegalAction


class RepositoryActionSpace(ActionSpace):
    name = "repository"
    operations = ("SCREEN_CHANGE", "ESTIMATE_RISK", "RECOMMEND_REVIEW")

    def legal_actions(self, state):
        changes = state.get("changes", [])
        legal = []
        for change in changes:
            cid = change.get("id", "?")
            legal.append(
                LegalAction(id=f"screen:{cid}", operation="SCREEN_CHANGE", target=cid, label=f"Screen {cid}")
            )
            legal.append(
                LegalAction(id=f"risk:{cid}", operation="ESTIMATE_RISK", target=cid, label=f"Estimate risk {cid}")
            )
            legal.append(
                LegalAction(
                    id=f"review:{cid}", operation="RECOMMEND_REVIEW", target=cid, label=f"Recommend review {cid}"
                )
            )
        return legal
