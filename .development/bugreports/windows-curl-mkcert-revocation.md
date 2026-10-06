# Windows cURL cannot establish revocation status for the local mkcert certificate

**Detected:** 2026-10-06.
**Candidate commit:** 9744e12 with the local broker access-log fix.
**Status:** Open; blocks the strict Windows cURL Matrix readiness check.

## Symptoms and verified findings

The direct Matrix versions request fails in Windows cURL/Schannel with
CRYPT_E_NO_REVOCATION_CHECK (0x80092012), before any Matrix response. The owner
asked to inspect the certificate dates and repeat the request. It was repeated
with the same TLS settings and produced the same error.

Caddyfile names /certs/agentschat.local.pem. Docker inspect confirms that
/certs is mounted from D:/AI/Quoroom/docker/caddy/certs. The public certificate
was inspected with certutil and X509Certificate2; no private key was read.

- Leaf SHA1 thumbprint: CAD7AC4027C1DB353C310E02FA5B3050C7DC0C4E.
- Leaf validity: 2026-09-06T16:29:06Z through 2028-12-06T17:29:06Z.
- Subject Alternative Name: agentschat.local.
- Leaf extensions: key usage, extended key usage, authority key identifier,
  and subject alternative name. No CRL distribution points or authority
  information access extension is present.
- Root SHA1 thumbprint: 0124878AD457ED76F4E35F63266798F065B4F620.
- Root validity: 2026-09-06T16:28:33Z through 2036-09-06T16:28:33Z.
- The root is present in CurrentUser/Root. Both certificates are time-valid.
- X509Chain with Online revocation checking builds those two chain elements
  but returns false with only RevocationStatusUnknown.

## Suspected current cause

The error is consistent with missing revocation information for this local
development certificate. Validity dates are present and valid; they do not
establish revocation status. A revocation date is not the certificate expiry
date. No time-valid CRL or OCSP result has been established by this diagnosis.

Microsoft's Crypt32 documentation describes separate CRL/OCSP retrieval for
revocation checking and CRL publication/expiry fields:
https://learn.microsoft.com/en-us/windows/win32/seccrypto/certificate-revocation-list-semantics

## Temporary decision

Stop under AGENTS.md rule 0.9. Restore the stopped Docker stack with volumes
preserved. Do not replace certificates, change Windows trust, disable TLS,
or change broker verify_ssl. The client, kit and session files are unchanged.

## Recommendation and later boundary

If explicitly authorized by the owner, use cURL's --ssl-revoke-best-effort
only for the local Matrix readiness request. It tolerates missing/offline
revocation distribution points while other TLS verification stays enabled.
The installed cURL help lists the flag. The owner subsequently authorized it
only for this local readiness request. The command below returned exit code 0
and Matrix versions through v1.18. The strict-check limitation remains; no
revocation result was established. Broker verify_ssl, certificates, Windows
trust and global settings were unchanged.

Reviewable command:

`curl.exe --ssl-revoke-best-effort --fail --silent --show-error https://agentschat.local/_matrix/client/versions`

Official option contract:
https://curl.se/docs/manpage.html#--ssl-revoke-best-effort

This recommendation does not authorize a global setting, a certificate
replacement, federation, or changes to unrelated tools or storage. It does
not claim that the certificate was proven unrevoked or that E2E has passed.
