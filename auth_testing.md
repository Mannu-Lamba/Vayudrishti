# Emergent Google Auth Testing Playbook

## Session model
- Google returns users to the browser origin with `#session_id=...`.
- The frontend must detect the fragment synchronously with `useLocation().hash` and render an auth callback before protected routes.
- The backend exchanges the temporary session id with `https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data` using `X-Session-ID`.
- The backend stores the returned `session_token` in `user_sessions`, stores user data in `users`, and sets an httpOnly `session_token` cookie with `secure=True`, `samesite="none"`, and `path="/"`.
- `/api/auth/me` is the source of truth for authenticated state. The frontend never stores or returns tokens.

## Test identity setup
Use a temporary Mongo user and session token for protected-route browser tests. Generate a custom `user_id` and ensure `user_sessions.user_id` matches it. Exclude Mongo `_id` from API projections. Do not store Google passwords.

```bash
mongosh --eval "
use('app');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({user_id: userId, email: 'test.user.' + Date.now() + '@example.com', name: 'Test User', picture: 'https://via.placeholder.com/150', created_at: new Date()});
db.user_sessions.insertOne({user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now() + 7*24*60*60*1000), created_at: new Date()});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Backend checks
```bash
curl -X GET "https://your-app.com/api/auth/me" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```
Expected: user data with `user_id`, `email`, `name`, and optional `picture`.

## Browser checks
Set an httpOnly `session_token` cookie for the preview domain, navigate to `/`, and verify the dashboard renders. Verify `/api/auth/me` returns the same user, the profile menu shows the user, and sign-out clears the session and returns to the login screen.

## Cleanup
Delete temporary test users and sessions by the generated `test.user.` email and `test_session` token pattern after testing.