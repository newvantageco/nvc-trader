import NextAuth from "next-auth"
import Credentials from "next-auth/providers/credentials"

const ALLOWED_EMAIL   = "sabanali19@outlook.com"

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email:    { label: "Email",    type: "email"    },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email    = credentials?.email    as string | undefined
        const password = credentials?.password as string | undefined

        if (!email || !password) return null

        // Single authorised user
        if (
          email.toLowerCase().trim() === ALLOWED_EMAIL &&
          password === process.env.DASHBOARD_PASSWORD
        ) {
          return {
            id:    "1",
            email: ALLOWED_EMAIL,
            name:  "Saban Ali",
          }
        }
        return null
      },
    }),
  ],

  pages: {
    signIn: "/login",
  },

  session: {
    strategy:  "jwt",
    maxAge:    7 * 24 * 60 * 60,   // 7 days
  },

  callbacks: {
    async jwt({ token, user }) {
      if (user) token.userId = user.id
      return token
    },
    async session({ session, token }) {
      if (session.user) (session.user as { id?: string }).id = token.userId as string
      return session
    },
  },

  secret: process.env.NEXTAUTH_SECRET,
})
