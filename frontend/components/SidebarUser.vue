<script setup lang="ts">
import { LogoutOutlined, LockOutlined } from '@ant-design/icons-vue'
import { apiPost } from '~/composables/useApi'

// 侧边栏底部用户卡片 — 接入 useAuth 登录态
const { isLogged, user, logout } = useAuth()
const msg = useMessage()

const showPasswordModal = ref(false)
const passwordForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const changingPassword = ref(false)

function onLogout() {
  logout()
  navigateTo('/login')
}

function openChangePassword() {
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  showPasswordModal.value = true
}

async function onChangePassword() {
  if (!passwordForm.oldPassword || !passwordForm.newPassword) {
    msg.warning('请填写完整')
    return
  }
  if (passwordForm.newPassword.length < 6) {
    msg.warning('新密码至少 6 个字符')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    msg.warning('两次输入的密码不一致')
    return
  }
  changingPassword.value = true
  try {
    await apiPost('/api/auth/change-password', {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword,
    })
    msg.success('密码修改成功，请重新登录')
    showPasswordModal.value = false
    onLogout()
  } catch (e: any) {
    msg.error(formatError(e, '修改失败'))
  } finally {
    changingPassword.value = false
  }
}

function onMenuClick({ key }: { key: string }) {
  if (key === 'logout') onLogout()
  else if (key === 'changePassword') openChangePassword()
}
</script>

<template>
  <div class="sidebar-footer">
    <template v-if="isLogged && user">
      <a-dropdown :trigger="['click']" style="width:100%;">
        <div class="sidebar-user">
          <a-avatar :size="34" :style="{ backgroundColor: 'var(--color-primary)', fontSize: '14px', fontWeight: 600 }">
            {{ (user.nickname || user.username || '?').charAt(0) }}
          </a-avatar>
          <div class="sidebar-user-info">
            <div class="sidebar-user-name">{{ user.nickname || user.username }}</div>
            <div class="sidebar-user-role">创作者</div>
          </div>
        </div>
        <template #overlay>
          <a-menu @click="onMenuClick">
            <a-menu-item key="changePassword">
              <LockOutlined />
              修改密码
            </a-menu-item>
            <a-menu-item key="logout">
              <LogoutOutlined />
              退出登录
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </template>
    <template v-else>
      <NuxtLink to="/login" class="sidebar-user">
        <a-avatar :size="34" :style="{ backgroundColor: '#ccc' }">?</a-avatar>
        <div class="sidebar-user-info">
          <div class="sidebar-user-name">未登录</div>
          <div class="sidebar-user-role">点击登录</div>
        </div>
      </NuxtLink>
    </template>

    <!-- 修改密码弹窗 -->
    <a-modal
      v-model:open="showPasswordModal"
      title="修改密码"
      :confirm-loading="changingPassword"
      @ok="onChangePassword"
    >
      <div style="display:flex;flex-direction:column;gap:16px;padding:8px 0;">
        <div>
          <label style="display:block;font-size:13px;font-weight:500;margin-bottom:6px;">旧密码</label>
          <a-input-password v-model:value="passwordForm.oldPassword" placeholder="输入当前密码" />
        </div>
        <div>
          <label style="display:block;font-size:13px;font-weight:500;margin-bottom:6px;">新密码</label>
          <a-input-password v-model:value="passwordForm.newPassword" placeholder="至少 6 个字符" />
        </div>
        <div>
          <label style="display:block;font-size:13px;font-weight:500;margin-bottom:6px;">确认新密码</label>
          <a-input-password v-model:value="passwordForm.confirmPassword" placeholder="再次输入新密码" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.sidebar-footer{padding:12px 16px;border-top:1px solid var(--color-border);}
.sidebar-user{display:flex;align-items:center;gap:10px;cursor:pointer;}
.sidebar-user-info{min-width:0;}
.sidebar-user-name{font-size:var(--text-sm);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sidebar-user-role{font-size:var(--text-xs);color:var(--color-fg-muted);}
a.sidebar-user{text-decoration:none;color:inherit;}
</style>
