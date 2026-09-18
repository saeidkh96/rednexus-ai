from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from sqlalchemy import select, update
from .storage import User, Membership, Workspace, SessionToken, LoginAttempt


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def password_hash(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${value.hex()}"


def password_matches(password, stored):
    try:
        _, salt, expected = stored.split("$")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Actor:
    id: str
    workspace: str
    username: str
    role: str
    grants: frozenset[str]
    kind: str

    def require_role(self, *roles):
        if self.role not in roles:
            raise Problem(403, "role does not permit this action")

    def require(self, grant):
        if grant not in self.grants:
            raise Problem(403, f"missing grant: {grant}")


def actor_for(s, user_id, workspace):
    u = s.get(User, user_id)
    m = s.get(Membership, (workspace, user_id))
    if not u or not m or not u.enabled or not m.enabled:
        raise Problem(401, "identity or membership inactive")
    return Actor(u.id, workspace, u.username, m.role, frozenset(m.grants), u.kind)


class Identity:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.dummy_hash = password_hash(secrets.token_urlsafe(20))

    def create_user(self, s, workspace, data):
        if s.scalar(select(User).where(User.username == data.username)):
            raise Problem(409, "username already exists; add membership via operator CLI")
        user = User(username=data.username, password_hash=password_hash(data.password), kind=data.kind)
        s.add(user)
        s.flush()
        s.add(Membership(workspace=workspace, user_id=user.id, role=data.role, grants=data.grants))
        return {"id": user.id, "username": user.username, "kind": user.kind, "role": data.role}

    def bootstrap(self, workspace, name, data):
        with self.db.session.begin() as s:
            if s.get(Workspace, workspace):
                raise Problem(409, "workspace exists; bootstrap never resets credentials")
            s.add(Workspace(id=workspace, name=name))
            return self.create_user(s, workspace, data)

    def login(self, data, remote):
        key = token_hash(f"{data.workspace}|{data.username.casefold()}")
        # Count every attempt atomically before expensive password verification.
        # Account-scoped limit is consistent across API processes.
        with self.db.session.begin() as s:
            record = s.get(LoginAttempt, key)
            if record is None:
                s.add(LoginAttempt(key=key, count=0, window=time.time()))
                s.flush()
            s.execute(
                update(LoginAttempt)
                .where(LoginAttempt.key == key, LoginAttempt.window < time.time() - 300)
                .values(count=0, window=time.time())
            )
            result = s.execute(
                update(LoginAttempt)
                .where(LoginAttempt.key == key, LoginAttempt.count < 10)
                .values(count=LoginAttempt.count + 1)
            )
            allowed = result.rowcount == 1
        if not allowed:
            raise Problem(429, "too many login attempts; try again after five minutes")
        with self.db.session.begin() as s:
            user = s.scalar(select(User).where(User.username == data.username))
            valid = password_matches(data.password, user.password_hash if user else self.dummy_hash)
            if not user or not valid:
                raise Problem(401, "invalid credentials or workspace")
            try:
                actor = actor_for(s, user.id, data.workspace)
            except Problem:
                raise Problem(401, "invalid credentials or workspace") from None
            token = secrets.token_urlsafe(40)
            s.add(
                SessionToken(
                    token_hash=token_hash(token),
                    user_id=actor.id,
                    workspace=actor.workspace,
                    expires=time.time() + self.settings.session_seconds,
                )
            )
            s.execute(update(LoginAttempt).where(LoginAttempt.key == key).values(count=0))
            return {"access_token": token, "token_type": "bearer", "expires_in": self.settings.session_seconds}

    def authenticate(self, token):
        with self.db.session() as s:
            record = s.get(SessionToken, token_hash(token))
            if not record or record.expires <= time.time():
                raise Problem(401, "session expired or invalid")
            return actor_for(s, record.user_id, record.workspace)

    def logout(self, token):
        with self.db.session.begin() as s:
            record = s.get(SessionToken, token_hash(token))
            if record:
                s.delete(record)


def consume_quota(db, key, limit, seconds):
    from .storage import RateBucket
    from sqlalchemy.exc import IntegrityError

    try:
        with db.session.begin() as s:
            if s.get(RateBucket, key) is None:
                s.add(RateBucket(key=key, count=0, window=time.time()))
                s.flush()
            s.execute(
                update(RateBucket)
                .where(RateBucket.key == key, RateBucket.window < time.time() - seconds)
                .values(count=0, window=time.time())
            )
            changed = s.execute(
                update(RateBucket)
                .where(RateBucket.key == key, RateBucket.count < limit)
                .values(count=RateBucket.count + 1)
            )
            if changed.rowcount != 1:
                raise Problem(429, "request quota exhausted; retry later")
    except IntegrityError:
        raise Problem(429, "concurrent quota initialization; retry later") from None
