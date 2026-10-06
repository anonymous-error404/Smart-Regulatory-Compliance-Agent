"""
src/rag/permission_filter.py
-----------------------------
Permission-Aware Pre-Filter for the Auris RAG pipeline.

Implements the "filter BEFORE ranking" strategy described in the ideation
document (§7).  Documents that a user is not cleared to see never enter the
retrieval candidates at all — the agent is structurally incapable of
seeing restricted content.

Filter Flow
-----------
1. Query arrives with user identity token (role string).
2. ACL table lookup in Snowflake (or config-based for demo).
3. Returns the set of permitted document categories + data scopes.
4. Cortex Search / local search runs ONLY over the permitted set.
5. Restricted docs never appear as candidates.
"""

from __future__ import annotations

import logging
from typing import Any

import config

logger = logging.getLogger(__name__)


# Clearance levels are resolved dynamically via config.get_role_config()


class PermissionFilter:
    """Look up and enforce document-level access control for RAG queries.

    In live mode (Snowpark session provided), reads from the
    ``USER_PERMISSIONS`` table.  In local/demo mode, resolves clearance
    levels and categories dynamically via ``config.get_role_config()``.

    Parameters
    ----------
    session : snowflake.snowpark.Session, optional
        Active Snowpark session for live ACL lookups.
    """

    def __init__(self, session: Any = None) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def get_allowed_categories(self, user_role: str) -> list[str]:
        """Return the list of document categories this role/rank may access.

        Parameters
        ----------
        user_role : str
            Role name or clearance rank string (e.g. 'Level 1', 'compliance_head').

        Returns
        -------
        list[str]
            Permitted document category strings.
        """
        if self.session is not None:
            return self._lookup_snowflake(user_role)
        return self._lookup_config(user_role)

    def get_permission_level(self, user_role: str) -> int:
        """Return the numeric clearance level for a role or rank string.

        Higher number = broader access level.

        Parameters
        ----------
        user_role : str
            Role name or clearance level string.

        Returns
        -------
        int
            Numeric clearance level (1, 2, 3, etc.).
        """
        cfg = config.get_role_config(user_role)
        return cfg.get("level", 1)

    def filter_documents(
        self,
        documents: list[dict],
        user_role: str,
    ) -> list[dict]:
        """Pre-filter a list of document chunks by user permissions.

        This is the core "filter BEFORE ranking" operation.  Only chunks
        whose ``permission_level`` and ``doc_category`` are within the
        user's clearance are returned.

        Parameters
        ----------
        documents : list[dict]
            Candidate document chunks, each with at least
            ``permission_level`` (str) and ``doc_category`` (str) keys.
        user_role : str
            The requesting user's role.

        Returns
        -------
        list[dict]
            Subset of *documents* that the user is permitted to see.
        """
        user_level = self.get_permission_level(user_role)
        allowed_categories = set(self.get_allowed_categories(user_role))

        filtered: list[dict] = []
        for doc in documents:
            doc_level_str = doc.get("permission_level", "junior_analyst")
            doc_level = self.get_permission_level(doc_level_str)
            doc_category = doc.get("doc_category", "public_policy")

            # Two-factor check: role level AND category
            if doc_level <= user_level and doc_category in allowed_categories:
                filtered.append(doc)
            else:
                logger.debug(
                    "[PermissionFilter] Blocked doc '%s' (level=%s, cat=%s) "
                    "for role=%s (level=%d, cats=%s)",
                    doc.get("doc_name", "?"),
                    doc_level_str,
                    doc_category,
                    user_role,
                    user_level,
                    allowed_categories,
                )

        logger.info(
            "[PermissionFilter] Filtered %d → %d docs for role='%s'",
            len(documents),
            len(filtered),
            user_role,
        )
        return filtered

    def build_cortex_filter(self, user_role: str) -> dict:
        """Build a Cortex Search filter clause for permission-scoped queries.

        Returns a dict suitable for passing as ``filter`` to the Cortex
        Search API, restricting results to permitted categories and
        permission levels.

        Parameters
        ----------
        user_role : str
            The requesting user's role.

        Returns
        -------
        dict
            Filter dict, e.g.::

                {
                    "@and": [
                        {"@in": {"PERMISSION_LEVEL": ["junior_analyst"]}},
                        {"@in": {"DOC_CATEGORY": ["public_policy", "aml_guidelines"]}}
                    ]
                }
        """
        user_level = self.get_permission_level(user_role)
        allowed_categories = self.get_allowed_categories(user_role)

        # Build list of allowed permission levels (all levels ≤ user's level)
        allowed_levels = [
            r_key for r_key, r_cfg in config.USER_ROLES.items()
            if r_cfg.get("level", 1) <= user_level
        ]

        return {
            "@and": [
                {"@in": {"PERMISSION_LEVEL": allowed_levels}},
                {"@in": {"DOC_CATEGORY": allowed_categories}},
            ]
        }

    # ------------------------------------------------------------------ #
    #  Private lookup methods                                              #
    # ------------------------------------------------------------------ #

    def _lookup_snowflake(self, user_role: str) -> list[str]:
        """Query USER_PERMISSIONS table for allowed doc categories."""
        try:
            sql = f"""
            SELECT ALLOWED_DOC_CATEGORIES
            FROM USER_PERMISSIONS
            WHERE ROLE = '{user_role}'
              AND ACTIVE = TRUE
            LIMIT 1
            """
            rows = self.session.sql(sql).collect()
            if rows:
                import json
                raw = rows[0]["ALLOWED_DOC_CATEGORIES"]
                if isinstance(raw, str):
                    return json.loads(raw)
                if isinstance(raw, list):
                    return raw
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "[PermissionFilter] Snowflake lookup failed, falling back to config: %s",
                exc,
            )
        return self._lookup_config(user_role)

    @staticmethod
    def _lookup_config(user_role: str) -> list[str]:
        """Look up allowed categories from config.USER_ROLES."""
        role_data = config.USER_ROLES.get(user_role, {})
        return role_data.get(
            "allowed_doc_categories",
            ["public_policy", "aml_guidelines"],
        )
