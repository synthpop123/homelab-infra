/**
 * The catalog the build wrote (scripts/catalog.ts), under the type it was
 * written from. Read through here, never from the JSON: TypeScript infers
 * a JSON import from the values it holds on the day, so a build without a
 * commit types `commit` as `null` and the page stops compiling.
 */
import data from "@/data/catalog.json"
import type { Catalog } from "../../scripts/catalog"

export const catalog = data as Catalog
