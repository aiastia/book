<script setup lang="ts">
// 系统设置（#5 SMTP 邮件配置）
import { apiGet, apiPut, apiPost } from '~/composables/useApi'
useHead({ title: '系统设置 — 墨语' })
const msg = useMessage()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

const smtp = reactive({
  smtp_host: '',
  smtp_port: 465,
  smtp_username: '',
  smtp_password: '',
  smtp_use_ssl: true,
  smtp_use_tls: false,
  smtp_from_email: '',
  smtp_from_name: '墨语',
  email_auth_enabled: false,
  email_register_enabled: false,
})

const presets: Record<string, any> = {
  qq: { smtp_host: 'smtp.qq.com', smtp_port: 465, smtp_use_ssl: true, smtp_use_tls: false, smtp_from_name: '墨语' },
  '163': { smtp_host: 'smtp.163.com', smtp_port: 465, smtp_use_ssl: true, smtp_use_tls: false, smtp_from_name: '墨语' },
  gmail: { smtp_host: 'smtp.gmail.com', smtp_port: 587, smtp_use_ssl: false, smtp_use_tls: true, smtp_from_name: '墨语' },
  outlook: { smtp_host: 'smtp.office365.com', smtp_port: 587, smtp_use_ssl: false, smtp_use_tls: true, smtp_from_name: '墨语' },
}
function applyPreset(key: string) {
  const p = presets[key]
  if (p) { Object.assign(smtp, p); msg.info(`已应用 ${key} 预设`) }
}

const testEmail = ref('')

async function loadConfig() {
  loading.value = true
  try {
    const r = await apiGet<any>('/api/admin/system/smtp')
    Object.assign(smtp, r)
  } catch (e: any) {
    // 非管理员会 403
    if (String(e).includes('403') || String(e).includes('管理员')) {
      msg.error('需要管理员权限')
    }
  } finally { loading.value = false }
}
async function onSave() {
  saving.value = true
  try {
    await apiPut('/api/admin/system/smtp', { ...smtp })
    msg.success('SMTP 配置已保存')
  } catch (e: any) { msg.error('保存失败：' + formatError(e)) }
  finally { saving.value = false }
}
async function onTest() {
  if (!testEmail.value.trim()) { msg.warning('请输入收件邮箱'); return }
  testing.value = true
  try {
    const r = await apiPost<{ ok: boolean; message: string }>('/api/admin/system/smtp/test', { to_email: testEmail.value })
    msg.success(r.message || '发送成功')
  } catch (e: any) { msg.error('发送失败：' + formatError(e)) }
  finally { testing.value = false }
}

onMounted(() => loadConfig())
</script>

<template>
	  <PageHeader title="系统设置" back="/books" />

  <div class="page-content">
    <a-spin :spinning="loading">
      <a-card title="📧 邮件服务（SMTP）" style="margin-bottom:16px">
        <a-alert
          message="配置 SMTP 后，可开启邮箱验证码登录和注册。配置存储在管理员账户中，全系统共用。"
          type="info" show-icon :closable="false" style="margin-bottom:16px"
        />

        <!-- 快速预设 -->
        <div style="margin-bottom:16px">
          <span style="font-size:13px;color:#595959;margin-right:8px">快速预设：</span>
          <a-button size="small" v-for="(_, key) in presets" :key="key" @click="applyPreset(key)" style="margin-right:6px">{{ key }}</a-button>
        </div>

        <a-form layout="vertical">
          <div class="form-row2">
            <a-form-item label="SMTP 服务器">
              <a-input v-model:value="smtp.smtp_host" placeholder="smtp.qq.com" />
            </a-form-item>
            <a-form-item label="端口">
              <a-input-number v-model:value="smtp.smtp_port" :min="1" :max="65535" style="width:100%" />
            </a-form-item>
          </div>
          <div class="form-row2">
            <a-form-item label="用户名（邮箱）">
              <a-input v-model:value="smtp.smtp_username" placeholder="your@qq.com" />
            </a-form-item>
            <a-form-item label="授权码 / 密码">
              <a-input-password v-model:value="smtp.smtp_password" placeholder="（QQ邮箱用授权码，非登录密码）" />
            </a-form-item>
          </div>
          <div class="form-row2">
            <a-form-item label="发件人邮箱">
              <a-input v-model:value="smtp.smtp_from_email" placeholder="通常与用户名相同" />
            </a-form-item>
            <a-form-item label="发件人名称">
              <a-input v-model:value="smtp.smtp_from_name" />
            </a-form-item>
          </div>
          <a-form-item label="加密方式">
            <a-radio-group v-model:value="smtp.smtp_use_ssl">
              <a-radio :value="true">SSL（端口 465）</a-radio>
              <a-radio :value="false">STARTTLS（端口 587）</a-radio>
            </a-radio-group>
          </a-form-item>

          <a-divider orientation="left">功能开关</a-divider>
          <a-form-item>
            <a-checkbox v-model:checked="smtp.email_auth_enabled">开启邮箱验证码登录</a-checkbox>
          </a-form-item>
          <a-form-item>
            <a-checkbox v-model:checked="smtp.email_register_enabled">开启邮箱注册</a-checkbox>
          </a-form-item>

          <a-space>
            <a-button type="primary" :loading="saving" @click="onSave">💾 保存配置</a-button>
          </a-space>
        </a-form>
      </a-card>

      <!-- 测试发送 -->
      <a-card title="🧪 发送测试邮件">
        <div style="display:flex;gap:10px;align-items:center">
          <a-input v-model:value="testEmail" placeholder="收件邮箱地址" style="width:300px" />
          <a-button type="primary" :loading="testing" :disabled="!smtp.smtp_host" @click="onTest">
            {{ testing ? '发送中…' : '发送测试' }}
          </a-button>
        </div>
        <div style="font-size:12px;color:#8C8C8C;margin-top:8px">
          提示：发送前请先保存配置。QQ邮箱需在设置中开启 SMTP 并获取授权码。
        </div>
      </a-card>
    </a-spin>
  </div>
</template>

<style scoped>
.form-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
</style>
