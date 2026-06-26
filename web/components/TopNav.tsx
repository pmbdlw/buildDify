'use client'

// 全局顶部导航:品牌 + 四模块入口(当前路由高亮)+ 当前用户 + 登出。
// 四个主模块页面统一引用,保证导航与鉴权态一致。
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { type User } from '@/lib/api'
import { logout } from '@/lib/auth'

const LINKS = [
  { href: '/chat', label: '对话' },
  { href: '/knowledge', label: '知识库' },
  { href: '/apps', label: '应用' },
  { href: '/workflows', label: '工作流' },
]

export default function TopNav({ user }: { user?: User | null }) {
  const pathname = usePathname()
  const router = useRouter()
  return (
    <header className="flex h-12 shrink-0 items-center gap-1 border-b border-gray-200 bg-white px-4">
      <Link href="/chat" className="mr-3 text-sm font-bold text-gray-900">
        buildDify
      </Link>
      <nav className="flex items-center gap-1">
        {LINKS.map((l) => {
          const active = pathname === l.href || pathname.startsWith(l.href + '/')
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-md px-3 py-1.5 text-sm transition ${
                active
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900'
              }`}
            >
              {l.label}
            </Link>
          )
        })}
      </nav>
      <div className="ml-auto flex items-center gap-3 text-sm text-gray-500">
        {user && <span className="hidden sm:inline">{user.email}</span>}
        <button onClick={() => logout(router)} className="hover:text-gray-900">
          登出
        </button>
      </div>
    </header>
  )
}
