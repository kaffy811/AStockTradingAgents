"""
CLI: create or promote an admin user — Phase MVP-R1.2.

Usage:
  python -m app.cli.create_admin --username alice --email alice@example.com --password s3cur3pw
  python -m app.cli.create_admin --promote --email alice@example.com

Run from the backend/ directory with DATABASE_URL set in environment.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import or_, select, update

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def _create_admin(username: str, email: str, password: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(or_(User.username == username, User.email == email))
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.is_admin:
                print(f"[OK] User '{existing.username}' already has is_admin=True.")
                return
            # Promote existing user
            existing.is_admin = True
            await db.commit()
            print(f"[OK] Promoted existing user '{existing.username}' to admin.")
            return

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            is_admin=True,
        )
        db.add(user)
        await db.commit()
        print(f"[OK] Created admin user '{username}' ({email}).")


async def _promote(email: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"[ERROR] No user found with email '{email}'.")
            sys.exit(1)
        if user.is_admin:
            print(f"[OK] User '{user.username}' is already admin.")
            return
        user.is_admin = True
        await db.commit()
        print(f"[OK] Promoted '{user.username}' ({email}) to admin.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote an admin user")
    parser.add_argument("--username", help="Username for new admin user")
    parser.add_argument("--email", required=True, help="Email address")
    parser.add_argument("--password", help="Password (min 8 chars)")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote existing user by email to admin (no new user created)",
    )
    args = parser.parse_args()

    if args.promote:
        asyncio.run(_promote(args.email))
    else:
        if not args.username or not args.password:
            parser.error("--username and --password are required unless using --promote")
        if len(args.password) < 8:
            parser.error("Password must be at least 8 characters")
        asyncio.run(_create_admin(args.username, args.email, args.password))


if __name__ == "__main__":
    main()
