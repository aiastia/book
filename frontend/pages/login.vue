<script setup lang="ts">
// 登录页（landing 布局）
import { apiPost } from '~/composables/useApi'
import { useAuth } from '~/composables/useAuth'
import { useProject } from '~/composables/useProject'

definePageMeta({ layout: 'landing' })
useHead({ title: '登录 — 墨语' })

const { saveLogin } = useAuth()
const { currentProjectId } = useProject()

const form = reactive({ username: '', password: '', remember: false })
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  error.value = ''
  if (!form.username.trim() || !form.password.trim()) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    const data = await apiPost<{ access_token: string; user: { id: number; username: string; nickname: string } }>(
      '/api/login',
      { username: form.username, password: form.password },
    )
    saveLogin(data.access_token, data.user)
    const target = currentProjectId.value ? `/dashboard?pid=${currentProjectId.value}` : '/books'
    await navigateTo(target)
  } catch (e: any) {
    error.value = formatError(e, '登录失败，请检查用户名和密码')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="login-logo">
        <div class="sidebar-brand-logo">M</div>
      </div>
      <h1 class="login-title">欢迎回来</h1>
      <p class="login-subtitle">登录 墨语 继续你的创作</p>

      <div class="login-form">
        <div class="form-item">
          <label class="form-label">用户名</label>
          <input v-model="form.username" type="text" class="form-input" placeholder="请输入用户名" @keyup.enter="onSubmit" />
        </div>
        <div class="form-item">
          <label class="form-label">密码</label>
          <input v-model="form.password" type="password" class="form-input" placeholder="请输入密码" @keyup.enter="onSubmit" />
        </div>
        <div class="form-row">
          <label class="checkbox-label">
            <input v-model="form.remember" type="checkbox" />
            <span>记住我</span>
          </label>
          <a href="#" class="login-link">忘记密码？</a>
        </div>
        <div v-if="error" class="error-msg">{{ error }}</div>
        <button class="login-btn" :disabled="loading" @click="onSubmit">
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </div>

      <p class="login-foot">
        还没有账号？<NuxtLink to="/register" class="login-link">去注册</NuxtLink>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-page);
  padding: 20px;
}
.login-card {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 40px;
  width: 100%;
  max-width: 380px;
  box-shadow: var(--shadow-lg);
  text-align: center;
}
.login-logo {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}
.login-title {
  font-size: var(--text-3xl);
  margin-bottom: 6px;
}
.login-subtitle {
  color: var(--color-fg-secondary);
  font-size: var(--text-sm);
  margin-bottom: 28px;
}
.login-form { text-align: left; }
.form-item { margin-bottom: 18px; }
.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-fg);
  margin-bottom: 6px;
}
.form-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 14px;
  box-sizing: border-box;
  transition: border-color 0.2s;
  outline: none;
}
.form-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(46, 125, 50, 0.1);
}
.form-input::placeholder { color: var(--color-fg-muted); }
.form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-fg-secondary);
  cursor: pointer;
}
.checkbox-label input { cursor: pointer; }
.error-msg {
  padding: 10px 14px;
  background: var(--color-danger-bg);
  color: var(--color-danger);
  border-radius: var(--radius-md);
  font-size: 13px;
  margin-bottom: 16px;
}
.login-btn {
  width: 100%;
  padding: 10px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.login-btn:hover { background: var(--color-primary-hover); }
.login-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.login-link {
  color: var(--color-primary);
  text-decoration: none;
  font-size: 13px;
}
.login-foot {
  margin-top: 24px;
  font-size: var(--text-sm);
  color: var(--color-fg-secondary);
}
</style>
