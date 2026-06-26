'use client'

// 鉴权态钩子:未登录跳 /login;已登录拉取当前用户。各页统一用,替代重复的 getToken 检查。
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { type User, clearToken, getMe, getToken } from '@/lib/api'

export interface AuthState {
  ready: boolean // 鉴权校验完成(可渲染受保护内容)
  user: User | null
}

export function useRequireAuth(): AuthState {
  const router = useRouter()
  const [state, setState] = useState<AuthState>({ ready: false, user: null })

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login')
      return
    }
    let alive = true
    void getMe()
      .then((user) => {
        if (alive) setState({ ready: true, user })
      })
      .catch(() => {
        // token 失效:清除并回登录
        clearToken()
        router.replace('/login')
      })
    return () => {
      alive = false
    }
  }, [router])

  return state
}

export function logout(router: { replace: (p: string) => void }): void {
  clearToken()
  router.replace('/login')
}
