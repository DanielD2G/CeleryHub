export async function ensureSchema() {
  const { getDb } = await import("./index.js");
  getDb(); // table creation happens inside getDb()
  console.log("[CeleryHub] Database schema ensured");
}
