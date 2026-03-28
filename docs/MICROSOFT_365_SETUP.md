# Microsoft 365 SMTP Configuration Guide

This guide explains how to configure Microsoft 365 for sending emails via SMTP in the NeuraLeads system.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Sender Mailboxes](#sender-mailboxes)
3. [Step 1: Enable SMTP AUTH](#step-1-enable-smtp-auth-for-mailboxes)
4. [Step 2: Disable Security Defaults](#step-2-disable-security-defaults)
5. [Step 3: Handle MFA / App Passwords](#step-3-handle-multi-factor-authentication-mfa)
6. [Step 4: Conditional Access (Alternative)](#step-4-conditional-access-alternative-to-security-defaults)
7. [Step 5: Configure in RA System](#step-5-configure-in-exzelon-ra-system)
8. [Testing Connection](#testing-connection)
9. [Troubleshooting](#troubleshooting)
10. [Security Best Practices](#security-best-practices)

---

## Prerequisites

- Microsoft 365 Admin account credentials
- Access to Microsoft 365 Admin Center
- Access to Microsoft Entra Admin Center (Azure AD)
- All sender mailbox accounts created in M365

## Sender Mailboxes

The following sender mailboxes are configured for cold email outreach:

| Email | Display Name | Status |
|-------|--------------|--------|
| Brian@exzelon.com | Brian from Exzelon | Cold-Ready |
| David@exzelon.com | David from Exzelon | Cold-Ready |
| Stacey@exzelon.com | Stacey from Exzelon | Cold-Ready |
| bretiney@exzelon.com | Bretiney from Exzelon | Cold-Ready |
| Imely@exzelon.com | Imely from Exzelon | Cold-Ready |
| Jane.rose@exzelon.com | Jane Rose from Exzelon | Cold-Ready |
| Robert@exzelon.com | Robert from Exzelon | Cold-Ready |
| Britney@exzelon.com | Britney from Exzelon | Cold-Ready |
| Steve@exzelon.com | Steve from Exzelon | Cold-Ready |
| Jane@exzelon.com | Jane from Exzelon | Cold-Ready |
| Zanemartin@exzelon.com | Zane Martin - Exzelon | Admin Account |

## SMTP Server Details

| Setting | Value |
|---------|-------|
| SMTP Server | smtp.office365.com |
| Port | 587 |
| Encryption | STARTTLS |
| Authentication | Required (SMTP AUTH) |

---

## Step 1: Enable SMTP AUTH for Mailboxes

SMTP AUTH must be enabled for each mailbox that will send emails. There are multiple ways to do this:

### Method 1: Microsoft 365 Admin Center (UI)

1. **Go to Microsoft 365 Admin Center**
   - URL: https://admin.microsoft.com
   - Sign in with admin credentials

2. **Navigate to Users**
   - Click **Users** → **Active users**

3. **Select a User**
   - Click on the user you want to enable SMTP AUTH for

4. **Open Mail Settings**
   - Click the **Mail** tab in the user details panel
   - Click **Manage email apps**

5. **Enable Authenticated SMTP**
   - Check the box for **Authenticated SMTP**
   - Click **Save changes**

6. **Repeat for each sender mailbox**

### Method 2: Exchange Admin Center

If you don't see the Mail tab in the Admin Center:

1. **Go to Exchange Admin Center**
   - URL: https://admin.exchange.microsoft.com
   - Sign in with admin credentials

2. **Navigate to Mailboxes**
   - Click **Recipients** → **Mailboxes**

3. **Select a Mailbox**
   - Click on the mailbox you want to configure

4. **Manage Email Apps**
   - Look for **Manage email apps settings** or **Email apps & mobile devices**
   - Enable **Authenticated SMTP**
   - Save changes

5. **Repeat for each sender mailbox**

### Method 3: PowerShell (Bulk Enable)

For enabling SMTP AUTH on multiple mailboxes at once:

#### Install Exchange Online PowerShell Module

Open PowerShell as Administrator and run:

```powershell
# Set execution policy (if needed)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install the Exchange Online Management module
Install-Module -Name ExchangeOnlineManagement -Force -AllowClobber

# Import the module
Import-Module ExchangeOnlineManagement
```

#### Connect to Exchange Online

```powershell
# Connect with admin credentials
Connect-ExchangeOnline -UserPrincipalName Zanemartin@exzelon.com
```

A browser window will open for authentication.

#### Enable SMTP AUTH for Individual Users

```powershell
# Enable for a single user
Set-CASMailbox -Identity "Brian@exzelon.com" -SmtpClientAuthenticationDisabled $false

# Enable for another user
Set-CASMailbox -Identity "David@exzelon.com" -SmtpClientAuthenticationDisabled $false
```

#### Enable SMTP AUTH for All Sender Mailboxes

```powershell
# Enable for all configured sender mailboxes
$senders = @(
    "Brian@exzelon.com",
    "David@exzelon.com",
    "Stacey@exzelon.com",
    "bretiney@exzelon.com",
    "Imely@exzelon.com",
    "Jane.rose@exzelon.com",
    "Robert@exzelon.com",
    "Britney@exzelon.com",
    "Steve@exzelon.com",
    "Jane@exzelon.com",
    "Zanemartin@exzelon.com"
)

foreach ($sender in $senders) {
    Set-CASMailbox -Identity $sender -SmtpClientAuthenticationDisabled $false
    Write-Host "Enabled SMTP AUTH for: $sender"
}
```

#### Enable SMTP AUTH for All Users in Organization

```powershell
# Enable for ALL mailboxes (use with caution)
Get-Mailbox -ResultSize Unlimited | Set-CASMailbox -SmtpClientAuthenticationDisabled $false
```

#### Verify SMTP AUTH Status

```powershell
# Check status for a specific user (False = enabled, True = disabled)
Get-CASMailbox -Identity "Brian@exzelon.com" | Select-Object SmtpClientAuthenticationDisabled

# Check status for all sender mailboxes
$senders | ForEach-Object {
    Get-CASMailbox -Identity $_ | Select-Object PrimarySmtpAddress, SmtpClientAuthenticationDisabled
}
```

#### Disconnect When Done

```powershell
Disconnect-ExchangeOnline -Confirm:$false
```

---

## Step 2: Disable Security Defaults

**IMPORTANT:** Azure AD Security Defaults blocks SMTP authentication by default. You MUST disable it for SMTP to work.

### Error You'll See If Security Defaults is Enabled

```
5.7.139 Authentication unsuccessful, user is locked by your organization's security defaults policy
```

### How to Disable Security Defaults

1. **Go to Microsoft Entra Admin Center**
   - URL: https://entra.microsoft.com
   - Sign in with admin credentials

2. **Navigate to Properties**
   - Click **Identity** → **Overview** → **Properties** (in left sidebar)
   - OR go directly to: https://entra.microsoft.com/#view/Microsoft_AAD_IAM/DirectoryProperties.ReactView

3. **Manage Security Defaults**
   - Scroll down and click **Manage Security defaults**

4. **Disable Security Defaults**
   - Set **Security defaults** to **Disabled**
   - Select a reason (e.g., "My organization is using Conditional Access")
   - Click **Save**

5. **Wait for Propagation**
   - Changes can take **15-30 minutes** to propagate across Microsoft's servers

### Alternative: Keep Security On with Conditional Access

If you want to maintain security while allowing SMTP, see [Step 4: Conditional Access](#step-4-conditional-access-alternative-to-security-defaults).

---

## Step 3: Handle Multi-Factor Authentication (MFA)

If MFA/2FA is enabled on sender accounts, regular passwords won't work for SMTP. You need to create App Passwords.

### Check if MFA is Enabled

1. Go to: https://mysignins.microsoft.com/security-info
2. Sign in with the sender account
3. If you see MFA methods listed (Authenticator, Phone, Email), MFA is enabled

### Create App Password

1. **Go to Security Info**
   - URL: https://mysignins.microsoft.com/security-info
   - Sign in with the account that needs the App Password

2. **Add Sign-in Method**
   - Click **+ Add sign-in method**

3. **Select App Password**
   - In the dropdown, select **App password**
   - Click **Add**

4. **Name and Create**
   - Enter a name like `SMTP` or `NeuraLeads`
   - Click **Next** or **Create**

5. **Copy the Password**
   - Copy the generated 16-character password (e.g., `abcd efgh ijkl mnop`)
   - **IMPORTANT:** This password is shown only once!
   - Remove spaces when using it: `abcdefghijklmnop`

### If "App Password" Option is Not Visible

The App Password option may not appear due to several reasons:

#### Reason 1: Security Defaults is Enabled
- Security Defaults blocks App Passwords
- Solution: Disable Security Defaults (see Step 2)

#### Reason 2: App Passwords Not Allowed by Admin
1. Go to: https://entra.microsoft.com
2. Navigate to: **Users** → **All users** → **Per-user MFA**
3. Click **Service settings** tab
4. Under **App passwords**, select **Allow users to create app passwords to sign in to non-browser apps**
5. Click **Save**

#### Reason 3: MFA Not Set Up for User
- App Passwords are only available when MFA is enabled
- Set up MFA first, then App Password option will appear

#### Reason 4: Conditional Access Blocking
- Some Conditional Access policies block App Passwords
- Review your CA policies

### Update Mailbox Password in System

After creating an App Password:

1. Go to the RA Admin Panel → **Mailboxes** page
2. Click Edit on the mailbox
3. Update the password field with the App Password (no spaces)
4. Save changes

---

## Step 4: Conditional Access (Alternative to Security Defaults)

Conditional Access provides granular control - keep MFA for regular users while allowing SMTP for sender accounts.

### Prerequisites
- Azure AD Premium P1 or P2 license
- Security Defaults must be disabled first

### Step 4.1: Create Security Group for Sender Accounts

1. Go to: https://entra.microsoft.com
2. Navigate to: **Identity** → **Groups** → **All groups**
3. Click **+ New group**
4. Configure:
   - **Group type**: Security
   - **Group name**: `SMTP Sender Accounts`
   - **Group description**: `Service accounts for email sending`
   - **Members**: Add all sender mailboxes (Brian@, David@, etc.)
5. Click **Create**

### Step 4.2: Create Policy - Require MFA for All Users

1. Go to: **Identity** → **Protection** → **Conditional Access** → **Policies**
2. Click **+ New policy**
3. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `Require MFA for All Users` |
| **Users** | Include: **All users** |
| **Users** | Exclude: Select **Users and groups** → Add `SMTP Sender Accounts` group |
| **Target resources** | **All cloud apps** |
| **Grant** | **Require multifactor authentication** |
| **Enable policy** | **On** |

4. Click **Create**

### Step 4.3: Create Policy - Allow SMTP for Sender Accounts

1. Click **+ New policy**
2. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `Allow SMTP for Sender Mailboxes` |
| **Users** | Include: Select `SMTP Sender Accounts` group |
| **Target resources** | **All cloud apps** OR **Office 365 Exchange Online** |
| **Conditions** | Client apps → Configure: **Yes** → Check only **Other clients** |
| **Grant** | **Grant access** (no additional requirements) |
| **Enable policy** | **On** |

3. Click **Create**

### Policy Summary

| Policy | Applies To | Result |
|--------|------------|--------|
| Require MFA for All Users | Everyone except senders | MFA required |
| Allow SMTP for Senders | Sender accounts only | No MFA, SMTP works |

### Wait for Propagation

Conditional Access policies can take **5-15 minutes** to take effect.

---

## Step 5: Configure in NeuraLeads System

### Settings Page Configuration

1. Go to **Settings** → **Outreach** tab
2. Select **Microsoft 365 (Direct Send)** as the Send Mode
3. Enter:
   - **M365 Admin Email**: `Zanemartin@exzelon.com`
   - **M365 Password**: App Password (if MFA) or regular password
   - **SMTP Host**: `smtp.office365.com` (auto-filled)
   - **SMTP Port**: `587` (auto-filled)
4. Click **Test M365 Connection** to verify
5. Click **Save Outreach Settings**

### Mailboxes Page

1. Go to **Mailboxes** page
2. Verify all sender mailboxes are listed with "Cold-Ready" status
3. Test individual mailbox connections using the **Test** button
4. Update any passwords if using App Passwords

---

## Testing Connection

### Test Script

Create a file `test_m365.py` with the following content:

```python
"""Test M365 SMTP Connection"""
import smtplib

EMAIL = "Zanemartin@exzelon.com"
PASSWORD = "your-app-password-here"  # Use App Password if MFA enabled

print(f"Testing M365 SMTP connection for {EMAIL}...")
print("-" * 50)

try:
    print("1. Connecting to smtp.office365.com:587...")
    server = smtplib.SMTP("smtp.office365.com", 587, timeout=20)

    print("2. Starting TLS encryption...")
    server.starttls()

    print("3. Authenticating...")
    server.login(EMAIL, PASSWORD)

    print("-" * 50)
    print("SUCCESS! M365 connection is working!")
    print("-" * 50)
    server.quit()

except smtplib.SMTPAuthenticationError as e:
    print(f"\nAUTHENTICATION FAILED: {e}")
    print("\nPossible causes:")
    print("  - Security Defaults still enabled (wait 15-30 min after disabling)")
    print("  - SMTP AUTH not enabled for user")
    print("  - Wrong password (use App Password if MFA enabled)")
    print("  - Conditional Access blocking the connection")

except smtplib.SMTPConnectError as e:
    print(f"\nCONNECTION FAILED: {e}")
    print("\nPossible causes:")
    print("  - Firewall blocking port 587")
    print("  - Network issues")

except Exception as e:
    print(f"\nERROR: {e}")
```

Run the test:
```bash
python test_m365.py
```

### Test via API

```bash
curl -X POST "http://localhost:8000/api/v1/settings/test-connection/m365" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Troubleshooting

### Error Code Reference

| Error Code | Message | Cause | Solution |
|------------|---------|-------|----------|
| 5.7.139 | User is locked by your organization's security defaults policy | Security Defaults enabled | Disable Security Defaults |
| 5.7.139 | Authentication unsuccessful, the request did not meet the criteria | MFA/CA blocking | Use App Password or configure CA |
| 535 | Authentication failed | Wrong password | Check password, use App Password |
| 535 | SMTP AUTH is disabled | SMTP AUTH not enabled | Enable SMTP AUTH for user |
| 550 | Mailbox not found | Invalid email | Verify email address |

### Common Issues and Solutions

#### Issue: "Security defaults policy" Error

**Error:**
```
5.7.139 Authentication unsuccessful, user is locked by your organization's security defaults policy
```

**Solution:**
1. Go to https://entra.microsoft.com
2. Identity → Overview → Properties
3. Click "Manage Security defaults"
4. Set to **Disabled**
5. Wait 15-30 minutes

#### Issue: "App Password" Option Not Showing

**Solutions:**
1. Ensure Security Defaults is disabled
2. Enable App Passwords in Per-user MFA settings:
   - https://entra.microsoft.com → Users → Per-user MFA → Service settings
   - Check "Allow users to create app passwords"
3. Ensure MFA is set up for the user first

#### Issue: Authentication Failed with Correct Password

**Solutions:**
1. If MFA is enabled, you MUST use an App Password
2. Regular passwords don't work with MFA
3. Create App Password at https://mysignins.microsoft.com/security-info

#### Issue: SMTP AUTH is Disabled Error

**Solutions:**
1. Enable SMTP AUTH for the user:
   - Exchange Admin Center → Recipients → Mailboxes
   - Select user → Manage email apps → Enable Authenticated SMTP
2. Or via PowerShell:
   ```powershell
   Set-CASMailbox -Identity "user@domain.com" -SmtpClientAuthenticationDisabled $false
   ```

#### Issue: Changes Not Taking Effect

**Solutions:**
1. Microsoft 365 changes can take **15-30 minutes** to propagate
2. Try again after waiting
3. Clear browser cache
4. Sign out and sign back in

#### Issue: Connection Timeout

**Solutions:**
1. Check firewall allows outbound port 587
2. Verify network connectivity
3. Try from a different network
4. Check if corporate firewall/proxy is blocking

### Verification Checklist

Use this checklist to verify your configuration:

- [ ] Security Defaults is **Disabled**
- [ ] SMTP AUTH is **Enabled** for all sender mailboxes
- [ ] If MFA enabled, **App Password** is created and being used
- [ ] Waited **15-30 minutes** after making changes
- [ ] Credentials are correct in RA System Settings
- [ ] Test connection shows **Success**

---

## Security Best Practices

1. **Use App Passwords** when MFA is enabled
2. **Create dedicated sender accounts** - don't use admin accounts for bulk sending
3. **Use Conditional Access** instead of disabling Security Defaults entirely
4. **Rotate passwords** regularly (every 90 days)
5. **Monitor sending activity** for unusual patterns
6. **Set daily send limits** to prevent abuse (configured in Settings → Business Rules)
7. **Enable audit logging** in M365 to track email activity
8. **Use a security group** for sender accounts for easier management

---

## Daily Send Limits

### Microsoft 365 Limits

| Limit Type | Value |
|------------|-------|
| Recipients per day | 10,000 |
| Recipients per message | 500 |
| Messages per day | No specific limit |

### NeuraLeads System Limits

| Setting | Default Value | Location |
|---------|---------------|----------|
| Daily send limit per mailbox | 30 emails | Settings → Business Rules |
| Cooldown between emails | 10 days | Settings → Business Rules |
| Max contacts per company/job | 4 | Settings → Business Rules |

---

## Quick Reference URLs

| Resource | URL |
|----------|-----|
| Microsoft 365 Admin Center | https://admin.microsoft.com |
| Exchange Admin Center | https://admin.exchange.microsoft.com |
| Microsoft Entra (Azure AD) | https://entra.microsoft.com |
| Security Defaults Settings | https://entra.microsoft.com/#view/Microsoft_AAD_IAM/DirectoryProperties.ReactView |
| Per-user MFA Settings | https://entra.microsoft.com → Users → Per-user MFA |
| Security Info (App Passwords) | https://mysignins.microsoft.com/security-info |
| Conditional Access Policies | https://entra.microsoft.com → Protection → Conditional Access |

---

## Support Resources

- [Microsoft 365 Admin Center](https://admin.microsoft.com)
- [Exchange Admin Center](https://admin.exchange.microsoft.com)
- [Microsoft 365 SMTP AUTH Documentation](https://docs.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/authenticated-client-smtp-submission)
- [App Passwords for MFA](https://support.microsoft.com/en-us/account-billing/manage-app-passwords-for-two-step-verification-d6dc8c6d-4bf7-4851-ad95-6d07799387e9)
- [Security Defaults Documentation](https://docs.microsoft.com/en-us/azure/active-directory/fundamentals/concept-fundamentals-security-defaults)
- [Conditional Access Documentation](https://docs.microsoft.com/en-us/azure/active-directory/conditional-access/overview)
