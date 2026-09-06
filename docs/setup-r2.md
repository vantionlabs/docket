# Cloudflare R2 setup

1. Create a bucket (e.g. `<client>-documents`).
2. Create an API token scoped to that bucket with **Object Read & Write**.
   Note: Account ID, Access Key ID, Secret Access Key → the `R2_*` vars in
   `backend/.env`.
3. Set bucket CORS (Settings → CORS policy) so the browser can PUT with a
   presigned URL:

```json
[
  {
    "AllowedOrigins": ["http://localhost:3000", "https://<frontend-domain>"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["content-type"],
    "MaxAgeSeconds": 3600
  }
]
```

Notes:
- The presigned PUT signs the Content-Type; the browser upload must send
  exactly the same header (the frontend's upload hook does).
- Objects are keyed `documents/<user_id>/<uuid>/<filename>`; deleting a
  document via the API also deletes the object.
