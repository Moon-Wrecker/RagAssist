import type { components } from "./schema";

type Schemas = components["schemas"];

export type Session = Schemas["SessionOut"];
export type User = Schemas["UserOut"];
export type Workspace = Schemas["WorkspaceOut"];
export type Role = Schemas["UserRole"];
export type LoginRequest = Schemas["LoginRequest"];
export type AcceptRequest = Schemas["AcceptRequest"];
export type Me = Schemas["MeOut"];
