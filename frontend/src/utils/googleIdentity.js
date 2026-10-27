let loading

/** Load GIS once; a failed load can be retried without reloading the app. */
export function loadGoogleIdentity() {
  if (window.google?.accounts?.id) return Promise.resolve()
  if (loading) return loading
  loading = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    const finish = (error) => {
      clearTimeout(timer)
      script.onload = script.onerror = null
      if (error) {
        script.remove()
        loading = undefined
        reject(error)
      } else resolve()
    }
    const timer = setTimeout(() => finish(new Error('加载 Google 登录超时，请检查网络后重试。')), 12000)
    script.onload = () => finish(window.google?.accounts?.id ? null : new Error('Google 登录加载失败，请重试。'))
    script.onerror = () => finish(new Error('无法加载 Google 登录，请检查网络后重试。'))
    document.head.appendChild(script)
  })
  return loading
}
