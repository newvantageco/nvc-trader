export { default } from 'next-auth/middleware'

export const config = {
  // Protect all dashboard routes — only /login, /api/auth/*, and static assets are public
  matcher: [
    '/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)',
  ],
}
