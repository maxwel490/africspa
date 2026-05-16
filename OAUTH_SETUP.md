# OAuth Authentication Setup Guide

## Overview

Africa SPA System supports OAuth authentication with Google and Apple (iCloud) accounts. This allows users to sign in using their existing Google or Apple accounts instead of creating separate passwords.

## Supported Providers

### 1. Google OAuth 2.0
- Allows users to sign in with their Google account
- Supports Gmail and Google Workspace accounts
- Automatic profile picture import
- Email-based user identification

### 2. Apple Sign In (iCloud)
- Allows users to sign in with their Apple ID
- Supports iCloud accounts
- Privacy-focused authentication
- Email masking support

## Setup Instructions

### Google OAuth Setup

1. **Create Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable Google+ API and Google OAuth2 API

2. **Configure OAuth Consent Screen**
   - Go to APIs & Services → OAuth consent screen
   - Choose "External" for user type
   - Fill in required application information
   - Add required scopes:
     - `email`
     - `profile`
     - `openid`

3. **Create OAuth Credentials**
   - Go to APIs & Services → Credentials
   - Click "Create Credentials" → "OAuth client ID"
   - Select "Web application"
   - Add authorized redirect URI: `http://localhost:5000/oauth/google/callback` (for development)
   - For production, use your actual domain: `https://yourdomain.com/oauth/google/callback`
   - Copy Client ID and Client Secret

4. **Environment Variables**
   ```bash
   export GOOGLE_CLIENT_ID="your-google-client-id"
   export GOOGLE_CLIENT_SECRET="your-google-client-secret"
   export BASE_URL="https://yourdomain.com"  # For production
   ```

### Apple Sign In Setup

1. **Apple Developer Account**
   - Go to [Apple Developer Portal](https://developer.apple.com/)
   - Enroll in Apple Developer Program ($99/year)
   - Create a new App ID or use existing one

2. **Configure Sign In with Apple**
   - Go to Certificates, Identifiers & Profiles
   - Select your App ID
   - Enable "Sign In with Apple" capability
   - Configure primary App ID

3. **Create Service ID**
   - Go to Identifiers → Click "+" → "Service ID"
   - Enter description and identifier
   - Enable "Sign In with Apple"
   - Add return URL: `https://yourdomain.com/oauth/apple/callback`

4. **Create Private Key**
   - Go to Keys → Click "+" → "Sign In with Apple"
   - Download the private key (.p8 file)
   - Note the Key ID

5. **Generate Client Secret**
   ```python
   import jwt
   import time
   from cryptography.hazmat.primitives import serialization
   
   # Load your private key
   with open('your_private_key.p8', 'r') as key_file:
       private_key = key_file.read()
   
   # Create JWT
   payload = {
       'iss': 'YOUR_TEAM_ID',
       'iat': int(time.time()),
       'exp': int(time.time()) + 86400 * 180,  # 6 months
       'aud': 'https://appleid.apple.com',
       'sub': 'YOUR_SERVICE_ID'
   }
   
   client_secret = jwt.encode(
       payload,
       private_key,
       algorithm='ES256',
       headers={'kid': 'YOUR_KEY_ID'}
   )
   ```

6. **Environment Variables**
   ```bash
   export APPLE_CLIENT_ID="your-service-id"
   export APPLE_CLIENT_SECRET="your-generated-jwt"
   export BASE_URL="https://yourdomain.com"
   ```

## Environment Configuration

### Development Environment
```bash
# Google OAuth
export GOOGLE_CLIENT_ID="your-dev-google-client-id"
export GOOGLE_CLIENT_SECRET="your-dev-google-client-secret"

# Apple Sign In (optional for development)
export APPLE_CLIENT_ID="your-dev-service-id"
export APPLE_CLIENT_SECRET="your-dev-client-secret"

# Base URL
export BASE_URL="http://localhost:5000"
```

### Production Environment
```bash
# Google OAuth
export GOOGLE_CLIENT_ID="your-prod-google-client-id"
export GOOGLE_CLIENT_SECRET="your-prod-google-client-secret"

# Apple Sign In
export APPLE_CLIENT_ID="your-prod-service-id"
export APPLE_CLIENT_SECRET="your-prod-client-secret"

# Base URL
export BASE_URL="https://yourdomain.com"
```

## OAuth User Flow

### New User Registration
1. User clicks "Sign in with Google/Apple"
2. Redirected to OAuth provider
3. User authenticates with their account
4. Provider redirects back with authorization code
5. System exchanges code for access token
6. System retrieves user information
7. New user account created with `pending` status
8. Admin approval required before access

### Existing User Login
1. User clicks "Sign in with Google/Apple"
2. OAuth authentication flow
3. System matches OAuth account to existing user
4. User logged in if account is active
5. Profile information updated

### Account Linking
1. User logs in with traditional password
2. Goes to profile settings
3. Clicks "Link Google Account" or "Link Apple ID"
4. OAuth authentication flow
5. Account linked successfully
6. User can now use OAuth for future logins

## Security Considerations

### OAuth Security
- Use HTTPS in production
- Validate redirect URIs
- Implement state parameter for CSRF protection
- Store client secrets securely
- Regularly rotate secrets

### User Account Security
- OAuth users created with `pending` status
- Admin approval required for activation
- Temporary passwords generated for OAuth users
- Account linking requires authentication

### Data Privacy
- Minimal data collected from OAuth providers
- Profile images stored securely
- OAuth tokens not stored permanently
- User can unlink OAuth accounts

## Troubleshooting

### Common Issues

1. **Redirect URI Mismatch**
   - Ensure redirect URI matches exactly in Google Console
   - Check for trailing slashes
   - Use HTTPS in production

2. **Client ID/Secret Issues**
   - Verify environment variables are set
   - Check for typos in credentials
   - Ensure correct client type selected

3. **User Account Creation Issues**
   - Check user preferences field exists
   - Verify database schema includes OAuth fields
   - Check for duplicate email/username

4. **Apple Sign In Issues**
   - Verify private key format
   - Check Team ID and Service ID
   - Ensure JWT is properly signed

### Debug Mode
Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Testing OAuth Locally
Use tools like:
- [OAuth Playground](https://developers.google.com/oauthplayground/)
- [ngrok](https://ngrok.com/) for local testing
- Browser developer tools

## Production Deployment

### Required Environment Variables
```bash
# OAuth Configuration
GOOGLE_CLIENT_ID=required
GOOGLE_CLIENT_SECRET=required
APPLE_CLIENT_ID=optional
APPLE_CLIENT_SECRET=optional
BASE_URL=required

# Security
SECRET_KEY=required
FORCE_HTTPS=1
```

### SSL Certificate
- Valid SSL certificate required
- OAuth providers require HTTPS
- Use Let's Encrypt or commercial certificate

### Domain Configuration
- Update OAuth console with production domain
- Configure DNS records
- Test redirect URIs thoroughly

## User Management

### Admin Approval Process
1. New OAuth users appear in user list with `pending` status
2. Admin reviews user information
3. Admin assigns role and salon
4. Admin activates user account
5. User receives notification

### Account Management
- Users can link/unlink OAuth accounts
- Admin can disable OAuth access
- Password reset still available
- Multi-factor authentication support

## API Endpoints

### OAuth Endpoints
- `GET /oauth/login/google` - Initiate Google OAuth
- `GET /oauth/login/apple` - Initiate Apple OAuth
- `GET /oauth/google/callback` - Google OAuth callback
- `POST /oauth/apple/callback` - Apple OAuth callback
- `GET /oauth/link/google` - Link Google account
- `GET /oauth/link/apple` - Link Apple account
- `GET /oauth/unlink/google` - Unlink Google account
- `GET /oauth/unlink/apple` - Unlink Apple account
- `GET /oauth/status` - Get OAuth status

### Profile Management
- OAuth account linking/unlinking
- Profile picture updates
- Password management
- Security settings

## Support

For OAuth implementation support:
1. Check this guide first
2. Review provider documentation
3. Enable debug logging
4. Contact system administrator

## Future Enhancements

Planned OAuth features:
- Microsoft Azure AD support
- Facebook Login support
- LinkedIn OAuth support
- Two-factor authentication with OAuth
- SAML integration
- Custom OAuth providers
