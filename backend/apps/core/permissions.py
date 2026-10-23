from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import Membership

WORKSPACE_HEADER = "HTTP_X_WORKSPACE_ID"


def resolve_membership(request):
    """Find the membership for the requested workspace (header) or the user's first one."""
    if getattr(request, "_membership_cache", None) is not None:
        return request._membership_cache
    user = request.user
    if not user or not user.is_authenticated:
        return None
    qs = Membership.objects.select_related("workspace").filter(user=user)
    wanted = request.META.get(WORKSPACE_HEADER)
    if wanted:
        try:
            membership = qs.get(workspace_id=int(wanted))
        except (ValueError, Membership.DoesNotExist):
            raise NotFound("Workspace not found.")
    else:
        membership = qs.order_by("created_at").first()
    request._membership_cache = membership
    return membership


class IsWorkspaceMember(BasePermission):
    """Authenticated + member of the active workspace. Sets request.workspace / request.membership.

    Write operations on settings-type endpoints require owner/admin (see IsWorkspaceManager).
    """

    message = "You are not a member of this workspace."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        membership = resolve_membership(request)
        if membership is None:
            raise PermissionDenied("No workspace available for this user.")
        request.membership = membership
        request.workspace = membership.workspace
        return True


class IsWorkspaceManager(IsWorkspaceMember):
    message = "Only workspace owners or admins can change these settings."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.membership.can_manage


class WorkspaceScopedMixin:
    """Every queryset is filtered by the active workspace. Never bypass this."""

    permission_classes = [IsWorkspaceMember]

    def get_queryset(self):
        return super().get_queryset().filter(workspace=self.request.workspace)

    def perform_create(self, serializer):
        serializer.save(workspace=self.request.workspace)
