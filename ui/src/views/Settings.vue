<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("settings.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error.load">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('action.get-configuration')"
          :description="error.load"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column :lg="10" :max="10">
        <cv-tile light>
          <cv-form @submit.prevent="configureModule">
            <cv-row>
              <cv-column :md="4" :max="4">
                <cv-number-input
                  :label="$t('settings.sync_interval_minutes')"
                  v-model.number="form.sync_interval_minutes"
                  :min="1"
                  :disabled="loading.load || loading.save"
                />
              </cv-column>
              <cv-column :md="4" :max="4">
                <cv-number-input
                  :label="$t('settings.embedding_dimension')"
                  v-model.number="form.embedding_dimension"
                  :min="1"
                  :disabled="loading.load || loading.save"
                />
              </cv-column>
              <cv-column :md="4" :max="4">
                <cv-number-input
                  :label="$t('settings.max_file_size_mb')"
                  v-model.number="form.max_file_size_mb"
                  :min="1"
                  :disabled="loading.load || loading.save"
                />
              </cv-column>
            </cv-row>
            <cv-row>
              <cv-column :md="6" :max="6">
                <cv-text-input
                  ref="embedding_provider"
                  :label="$t('settings.embedding_provider')"
                  v-model="form.embedding_provider"
                  :disabled="loading.load || loading.save"
                  :invalid-message="error.embedding_provider"
                />
              </cv-column>
              <cv-column :md="6" :max="6">
                <cv-text-input
                  :label="$t('settings.embedding_model')"
                  v-model="form.embedding_model"
                  :disabled="loading.load || loading.save"
                  :invalid-message="error.embedding_model"
                />
              </cv-column>
            </cv-row>

            <div class="section-title">{{ $t("settings.users_title") }}</div>
            <cv-text-area
              ref="usersText"
              :label="$t('settings.users_text')"
              :helper-text="$t('settings.users_help')"
              v-model="form.usersText"
              :disabled="loading.load || loading.save"
              :invalid-message="error.usersText"
            />

            <div class="section-title">{{ $t("settings.sources_title") }}</div>

            <div v-for="source in sourceKeys" :key="source" class="source-card">
              <cv-row>
                <cv-column :md="3" :max="3">
                  <cv-toggle
                    :label="$t(`settings.sources.${source}.enabled`)"
                    value="true"
                    :checked="form.sources[source].enabled"
                    @change="toggleSource(source, $event)"
                  />
                </cv-column>
                <cv-column :md="4" :max="4">
                  <cv-text-input
                    :label="$t(`settings.sources.${source}.instance`)"
                    v-model="form.sources[source].instance"
                    :disabled="loading.load || loading.save"
                  />
                </cv-column>
                <cv-column v-if="source === 'nextcloud'" :md="5" :max="5">
                  <cv-text-input
                    :label="$t('settings.sources.nextcloud.mode')"
                    v-model="form.sources.nextcloud.mode"
                    :disabled="loading.load || loading.save"
                  />
                </cv-column>
                <cv-column v-if="source === 'samba'" :md="5" :max="5">
                  <cv-text-input
                    :label="$t('settings.sources.samba.shares')"
                    v-model="form.sources.samba.sharesText"
                    :disabled="loading.load || loading.save"
                    :helper-text="$t('settings.sources.samba.shares_help')"
                  />
                </cv-column>
              </cv-row>
            </div>

            <cv-row v-if="error.save">
              <cv-column>
                <NsInlineNotification
                  kind="error"
                  :title="$t('action.configure-module')"
                  :description="error.save"
                  :showCloseButton="false"
                />
              </cv-column>
            </cv-row>

            <div class="button-row">
              <NsButton
                kind="primary"
                :loading="loading.save"
                :disabled="loading.load || loading.save"
              >
                {{ $t("settings.save") }}
              </NsButton>
            </div>
          </cv-form>
        </cv-tile>
      </cv-column>
    </cv-row>
  </cv-grid>
</template>

<script>
import to from "await-to-js";
import { mapState } from "vuex";
import {
  QueryParamService,
  UtilService,
  TaskService,
  PageTitleService,
} from "@nethserver/ns8-ui-lib";

const EMPTY_FORM = () => ({
  sync_interval_minutes: 30,
  embedding_provider: "local",
  embedding_model: "BAAI/bge-m3",
  embedding_dimension: 1024,
  max_file_size_mb: 100,
  usersText: "",
  sources: {
    nextcloud: { enabled: false, instance: "", mode: "groupfolders" },
    samba: { enabled: false, instance: "", sharesText: "" },
    webtop: { enabled: false, instance: "" },
    nethvoice: { enabled: false, instance: "" },
    mattermost: { enabled: false, instance: "" },
  },
});

export default {
  name: "Settings",
  mixins: [TaskService, QueryParamService, UtilService, PageTitleService],
  pageTitle() {
    return this.$t("settings.title") + " - " + this.appName;
  },
  data() {
    return {
      q: {
        page: "settings",
      },
      urlCheckInterval: null,
      sourceKeys: ["nextcloud", "samba", "webtop", "nethvoice", "mattermost"],
      form: EMPTY_FORM(),
      loading: {
        load: false,
        save: false,
      },
      error: {
        load: "",
        save: "",
        embedding_provider: "",
        embedding_model: "",
        usersText: "",
      },
    };
  },
  computed: {
    ...mapState(["instanceName", "core", "appName"]),
  },
  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.watchQueryData(vm);
      vm.urlCheckInterval = vm.initUrlBindingForApp(vm, vm.q.page);
    });
  },
  beforeRouteLeave(to, from, next) {
    clearInterval(this.urlCheckInterval);
    next();
  },
  created() {
    this.loadState();
  },
  methods: {
    toggleSource(source, event) {
      this.form.sources[source].enabled = event.target.checked;
    },
    parseUsersText() {
      const users = [];
      const lines = this.form.usersText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);

      for (const line of lines) {
        const [principal_id, username] = line
          .split(",")
          .map((value) => value && value.trim());
        if (!principal_id || !username) {
          return { error: this.$t("settings.invalid_users") };
        }
        users.push({ principal_id, username });
      }

      return { users };
    },
    applyConfiguration(configuration) {
      this.form = {
        sync_interval_minutes: configuration.sync_interval_minutes || 30,
        embedding_provider: configuration.embedding_provider || "local",
        embedding_model: configuration.embedding_model || "BAAI/bge-m3",
        embedding_dimension: configuration.embedding_dimension || 1024,
        max_file_size_mb: configuration.max_file_size_mb || 100,
        usersText: (configuration.users || [])
          .map((user) => `${user.principal_id},${user.username}`)
          .join("\n"),
        sources: {
          nextcloud: {
            enabled: configuration.sources?.nextcloud?.enabled || false,
            instance: configuration.sources?.nextcloud?.instance || "",
            mode: configuration.sources?.nextcloud?.mode || "groupfolders",
          },
          samba: {
            enabled: configuration.sources?.samba?.enabled || false,
            instance: configuration.sources?.samba?.instance || "",
            sharesText: (configuration.sources?.samba?.shares || []).join(", "),
          },
          webtop: {
            enabled: configuration.sources?.webtop?.enabled || false,
            instance: configuration.sources?.webtop?.instance || "",
          },
          nethvoice: {
            enabled: configuration.sources?.nethvoice?.enabled || false,
            instance: configuration.sources?.nethvoice?.instance || "",
          },
          mattermost: {
            enabled: configuration.sources?.mattermost?.enabled || false,
            instance: configuration.sources?.mattermost?.instance || "",
          },
        },
      };
    },
    async runModuleAction(action, { data = {}, onComplete, onAborted } = {}) {
      const eventId = this.getUuid();
      this.core.$root.$once(
        `${action}-completed-${eventId}`,
        (taskContext, taskResult) =>
          onComplete && onComplete(taskContext, taskResult)
      );
      this.core.$root.$once(
        `${action}-aborted-${eventId}`,
        (taskResult, taskContext) =>
          onAborted && onAborted(taskResult, taskContext)
      );

      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action,
          data,
          extra: {
            title: this.$t(`action.${action}`),
            isNotificationHidden: true,
            eventId,
          },
        })
      );
      return res[0];
    },
    async loadState() {
      this.loading.load = true;
      this.error.load = "";

      const defaultsError = await this.runModuleAction("get-defaults", {
        onComplete: (taskContext, taskResult) => {
          this.applyConfiguration(taskResult.output);
        },
      });

      if (defaultsError) {
        this.error.load = this.getErrorMessage(defaultsError);
        this.loading.load = false;
        return;
      }

      const configError = await this.runModuleAction("get-configuration", {
        onComplete: (taskContext, taskResult) => {
          this.applyConfiguration(taskResult.output.configuration || {});
          this.loading.load = false;
        },
        onAborted: () => {
          this.error.load = this.$t("error.generic_error");
          this.loading.load = false;
        },
      });

      if (configError) {
        this.error.load = this.getErrorMessage(configError);
        this.loading.load = false;
      }
    },
    validateForm() {
      this.clearErrors(this);
      let valid = true;

      if (!this.form.embedding_provider) {
        this.error.embedding_provider = this.$t("common.required");
        valid = false;
      }

      if (!this.form.embedding_model) {
        this.error.embedding_model = this.$t("common.required");
        valid = false;
      }

      const parsedUsers = this.parseUsersText();
      if (parsedUsers.error) {
        this.error.usersText = parsedUsers.error;
        valid = false;
      }

      return valid;
    },
    buildPayload() {
      const parsedUsers = this.parseUsersText();
      return {
        sync_interval_minutes: Number(this.form.sync_interval_minutes),
        embedding_provider: this.form.embedding_provider,
        embedding_model: this.form.embedding_model,
        embedding_dimension: Number(this.form.embedding_dimension),
        max_file_size_mb: Number(this.form.max_file_size_mb),
        users: parsedUsers.users || [],
        sources: {
          nextcloud: {
            enabled: this.form.sources.nextcloud.enabled,
            instance: this.form.sources.nextcloud.instance,
            mode: this.form.sources.nextcloud.mode,
          },
          samba: {
            enabled: this.form.sources.samba.enabled,
            instance: this.form.sources.samba.instance,
            shares: this.form.sources.samba.sharesText
              .split(",")
              .map((value) => value.trim())
              .filter(Boolean),
            share_group_map: {},
          },
          webtop: {
            enabled: this.form.sources.webtop.enabled,
            instance: this.form.sources.webtop.instance,
            contacts: true,
            calendars: true,
            mail: false,
          },
          nethvoice: {
            enabled: this.form.sources.nethvoice.enabled,
            instance: this.form.sources.nethvoice.instance,
            phonebook: true,
            transcriptions: true,
            recordings: false,
          },
          mattermost: {
            enabled: this.form.sources.mattermost.enabled,
            instance: this.form.sources.mattermost.instance,
            posts: true,
            files: true,
            direct_messages: false,
          },
        },
      };
    },
    async configureModule() {
      if (!this.validateForm()) {
        return;
      }

      this.loading.save = true;
      this.error.save = "";
      const error = await this.runModuleAction("configure-module", {
        data: this.buildPayload(),
        onComplete: () => {
          this.loading.save = false;
          this.loadState();
        },
        onAborted: () => {
          this.error.save = this.$t("error.generic_error");
          this.loading.save = false;
        },
      });

      if (error) {
        this.error.save = this.getErrorMessage(error);
        this.loading.save = false;
      }
    },
  },
};
</script>

<style scoped lang="scss">
.section-title {
  font-weight: 600;
  margin: 2rem 0 1rem;
}

.source-card {
  border-top: 1px solid #e0e0e0;
  margin-top: 1rem;
  padding-top: 1rem;
}

.button-row {
  margin-top: 2rem;
}
</style>
