export { auth as middleware } from "@/auth"

export const config = {
  // Protect everything except login page and NextAuth API routes
  matcher: ["/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)"],
}
