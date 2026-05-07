import crypto from "node:crypto";
import fs from "node:fs";

const envPath = new URL("../.env", import.meta.url);

if (!fs.existsSync(envPath)) {
  console.error(".env not found");
  process.exit(1);
}

const envText = fs.readFileSync(envPath, "utf8");

for (const line of envText.split(/\r?\n/)) {
  const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
  if (!match) continue;

  const [, key, rawValue] = match;
  let value = rawValue.trim();
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1);
  }
  process.env[key] = value;
}

const required = [
  "X_ACCOUNT_NAME",
  "X_CONSUMER_KEY",
  "X_CONSUMER_SECRET",
  "X_ACCESS_TOKEN",
  "X_ACCESS_TOKEN_SECRET",
];

const missing = required.filter((key) => !process.env[key]);

for (const key of [
  "X_CLIENT_ID",
  "X_CLIENT_SECRET",
  "X_ACCESS_TOKEN",
  "X_ACCESS_TOKEN_SECRET",
  "X_BEARER_TOKEN",
  "X_CONSUMER_KEY",
  "X_CONSUMER_SECRET",
]) {
  console.log(`${key}: ${process.env[key] ? "set" : "missing"}`);
}

if (missing.length > 0) {
  console.error(`Missing required OAuth 1.0a keys: ${missing.join(", ")}`);
  process.exit(1);
}

const endpoint = "https://api.x.com/1.1/account/verify_credentials.json";
const params = { skip_status: "true", include_email: "false" };
const oauth = {
  oauth_consumer_key: process.env.X_CONSUMER_KEY,
  oauth_token: process.env.X_ACCESS_TOKEN,
  oauth_nonce: crypto.randomBytes(16).toString("hex"),
  oauth_timestamp: Math.floor(Date.now() / 1000).toString(),
  oauth_signature_method: "HMAC-SHA1",
  oauth_version: "1.0",
};

const encode = (value) =>
  encodeURIComponent(value).replace(/[!'()*]/g, (char) =>
    `%${char.charCodeAt(0).toString(16).toUpperCase()}`,
  );

const signatureParams = { ...params, ...oauth };
const paramString = Object.keys(signatureParams)
  .sort()
  .map((key) => `${encode(key)}=${encode(signatureParams[key])}`)
  .join("&");

const baseString = ["GET", encode(endpoint), encode(paramString)].join("&");
const signingKey = `${encode(process.env.X_CONSUMER_SECRET)}&${encode(
  process.env.X_ACCESS_TOKEN_SECRET,
)}`;

oauth.oauth_signature = crypto
  .createHmac("sha1", signingKey)
  .update(baseString)
  .digest("base64");

const authHeader =
  "OAuth " +
  Object.keys(oauth)
    .sort()
    .map((key) => `${encode(key)}="${encode(oauth[key])}"`)
    .join(", ");

const url = `${endpoint}?${new URLSearchParams(params)}`;
const response = await fetch(url, {
  headers: {
    Authorization: authHeader,
    "User-Agent": "ai-broadcast-hub-auth-check",
  },
});

const body = await response.text();
console.log(`verify_credentials_status: ${response.status}`);

let data;
try {
  data = JSON.parse(body);
} catch {
  console.error(body.slice(0, 300));
  process.exit(1);
}

if (!response.ok) {
  console.error(JSON.stringify(data.errors || data).slice(0, 500));
  process.exit(1);
}

console.log(`screen_name: ${data.screen_name || "(none)"}`);
console.log(`id_str: ${data.id_str || "(none)"}`);

if (process.env.X_ACCOUNT_NAME && data.screen_name !== process.env.X_ACCOUNT_NAME) {
  console.error(
    `Account mismatch: expected ${process.env.X_ACCOUNT_NAME}, got ${data.screen_name}`,
  );
  process.exit(1);
}

console.log("x_auth_check: ok");
