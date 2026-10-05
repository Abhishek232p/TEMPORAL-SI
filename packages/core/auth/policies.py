from fastapi import HTTPException, status
from packages.core.auth.context import AuthContext

class Policy:
    @staticmethod
    def can_view(auth: AuthContext):
        pass # All roles can view

    @staticmethod
    def can_update_org(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role")

    @staticmethod
    def can_delete_org(auth: AuthContext):
        if auth.role != 'OWNER':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER role")
            
    @staticmethod
    def can_manage_members(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role")

    @staticmethod
    def can_modify_target_role(auth: AuthContext, target_role: str):
        if auth.role == 'ADMIN' and target_role == 'OWNER':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ADMIN cannot manage OWNER roles")

    @staticmethod
    def can_manage_projects(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role to manage projects")

    @staticmethod
    def can_manage_datasets(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role to manage datasets")
