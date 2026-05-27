<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>钱包管理</template>
          <el-form label-position="top" size="small">
            <el-form-item label="私钥 (MetaMask)">
              <el-input v-model="walletForm.private_key" type="password" show-password placeholder="0x..." />
            </el-form-item>
            <el-form-item label="Funder 地址">
              <el-input v-model="walletForm.funder_address" placeholder="0x..." />
            </el-form-item>
            <el-form-item label="链 ID">
              <el-radio-group v-model="walletForm.chain_id">
                <el-radio :value="137">主网 (137)</el-radio>
                <el-radio :value="80002">测试网 (80002)</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="walletLoading" @click="setupWallet">配置钱包</el-button>
            </el-form-item>
          </el-form>

          <el-divider>已有钱包</el-divider>
          <el-table :data="wallets" size="small">
            <el-table-column prop="wallet_address" label="地址" show-overflow-tooltip />
            <el-table-column prop="chain_id" label="链" width="80" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '活跃' : '停用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button v-if="row.is_active" size="small" type="warning" @click="deactivate(row.id)">停用</el-button>
                <el-button v-else size="small" type="success" @click="activate(row.id)">启用</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>推送通知</template>
          <el-tabs v-model="notifyTab">
            <el-tab-pane label="方糖" name="serverchan">
              <el-form label-position="top" size="small">
                <el-form-item label="SendKey">
                  <el-input v-model="scForm.sendkey" placeholder="方糖 SendKey" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveNotify('serverchan')">保存</el-button>
                  <el-button @click="testNotify('serverchan')">测试</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
            <el-tab-pane label="Telegram" name="telegram">
              <el-form label-position="top" size="small">
                <el-form-item label="Bot Token">
                  <el-input v-model="tgForm.bot_token" placeholder="123456:ABC-DEF..." />
                </el-form-item>
                <el-form-item label="Chat ID">
                  <el-input v-model="tgForm.chat_id" placeholder="Chat ID" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveNotify('telegram')">保存</el-button>
                  <el-button @click="testNotify('telegram')">测试</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>

          <el-divider>已配置</el-divider>
          <el-table :data="notifyConfigs" size="small">
            <el-table-column prop="channel" label="渠道" width="100" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="danger" link @click="deleteNotify(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { walletApi, notifyApi } from '../api'
import { ElMessage } from 'element-plus'

const walletLoading = ref(false)
const wallets = ref<any[]>([])
const notifyConfigs = ref<any[]>([])
const notifyTab = ref('serverchan')

const walletForm = reactive({ private_key: '', funder_address: '', chain_id: 137 })
const scForm = reactive({ sendkey: '' })
const tgForm = reactive({ bot_token: '', chat_id: '' })

async function setupWallet() {
  walletLoading.value = true
  try {
    await walletApi.setup(walletForm)
    ElMessage.success('钱包配置成功')
    loadWallets()
  } catch {} finally { walletLoading.value = false }
}

async function loadWallets() {
  try {
    const { data } = await walletApi.list()
    wallets.value = data
  } catch {}
}

async function deactivate(id: number) {
  await walletApi.deactivate(id)
  loadWallets()
}

async function activate(id: number) {
  await walletApi.activate(id)
  loadWallets()
}

async function saveNotify(channel: string) {
  const config = channel === 'serverchan' ? { sendkey: scForm.sendkey } : { bot_token: tgForm.bot_token, chat_id: tgForm.chat_id }
  try {
    await notifyApi.saveConfig({ channel, config })
    ElMessage.success('推送配置已保存')
    loadNotifyConfigs()
  } catch {}
}

async function testNotify(channel: string) {
  try {
    await notifyApi.test({ channel })
    ElMessage.success('测试消息已发送')
  } catch {}
}

async function loadNotifyConfigs() {
  try {
    const { data } = await notifyApi.getConfig()
    notifyConfigs.value = data
  } catch {}
}

async function deleteNotify(id: number) {
  await notifyApi.deleteConfig(id)
  loadNotifyConfigs()
}

onMounted(() => {
  loadWallets()
  loadNotifyConfigs()
})
</script>
