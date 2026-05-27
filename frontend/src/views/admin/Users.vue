<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>用户管理</span>
          <el-radio-group v-model="statusFilter" size="small" @change="loadUsers">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="pending">待审核</el-radio-button>
            <el-radio-button value="approved">已通过</el-radio-button>
            <el-radio-button value="rejected">已拒绝</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <el-table :data="users" size="small" v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="role" label="角色" width="80">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : ''" size="small">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="180" />
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="success" @click="approve(row.id)">通过</el-button>
              <el-button size="small" type="warning" @click="reject(row.id)">拒绝</el-button>
            </template>
            <el-button size="small" type="primary" @click="openChangePwd(row)">改密</el-button>
            <el-button size="small" type="danger" @click="remove(row.id)" :disabled="row.role === 'admin'">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showChangePwd" title="修改密码" width="400">
      <p style="margin-bottom:12px;color:#666">用户: {{ changePwdUser?.username }}</p>
      <el-form label-position="top" size="small">
        <el-form-item label="新密码">
          <el-input v-model="newPassword" type="password" show-password placeholder="输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showChangePwd = false">取消</el-button>
        <el-button type="primary" @click="doChangePwd" :loading="changingPwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { adminApi } from '../../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(false)
const users = ref<any[]>([])
const statusFilter = ref('')
const showChangePwd = ref(false)
const changePwdUser = ref<any>(null)
const newPassword = ref('')
const changingPwd = ref(false)

function statusType(s: string) {
  return s === 'approved' ? 'success' : s === 'pending' ? 'warning' : 'danger'
}
function statusLabel(s: string) {
  return s === 'approved' ? '已通过' : s === 'pending' ? '待审核' : '已拒绝'
}

async function loadUsers() {
  loading.value = true
  try {
    const { data } = await adminApi.getUsers(statusFilter.value || undefined)
    users.value = data
  } catch {} finally { loading.value = false }
}

async function approve(id: number) {
  await adminApi.approve(id)
  ElMessage.success('已通过')
  loadUsers()
}

async function reject(id: number) {
  await adminApi.reject(id)
  ElMessage.success('已拒绝')
  loadUsers()
}

async function remove(id: number) {
  await ElMessageBox.confirm('确认删除该用户？', '警告', { type: 'warning' })
  await adminApi.deleteUser(id)
  ElMessage.success('已删除')
  loadUsers()
}

function openChangePwd(row: any) {
  changePwdUser.value = row
  newPassword.value = ''
  showChangePwd.value = true
}

async function doChangePwd() {
  if (!newPassword.value || newPassword.value.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  changingPwd.value = true
  try {
    await adminApi.changePassword(changePwdUser.value.id, { new_password: newPassword.value })
    ElMessage.success('密码已修改')
    showChangePwd.value = false
  } catch {} finally { changingPwd.value = false }
}

onMounted(loadUsers)
</script>
