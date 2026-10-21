# NestJS

Mechanics for editing an existing NestJS backend. NestJS is usually API-only: legal pages and the banner then live in the project's frontend stack file (`nextjs.md`, `react.md`, `react-native.md`, ...), and NestJS contributes the consent-log endpoint, server-side enforcement of the consent field, and optionally the document endpoints. The knowledge pack decides which forms need consent; this file shows the mechanics. Add no new libraries beyond what the project already has.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- `package.json` has `@nestjs/core`; `nest-cli.json`, `src/main.ts`, `src/app.module.ts`. HTTP adapter: `@nestjs/platform-express` or `@nestjs/platform-fastify` (check `main.ts` for `NestFactory.create<...>`).
- ORM/DB (decides whether a consent log is allowed): `@nestjs/typeorm` (entities `*.entity.ts`), `@prisma/client` + a `PrismaService`, `@mikro-orm/nestjs`, `@nestjs/sequelize`, `@nestjs/mongoose`, `drizzle-orm`. None of them: no consent log.
- Validation: `class-validator` + `ValidationPipe` (check `app.useGlobalPipes` in `main.ts`), or `nestjs-zod`. Config: `@nestjs/config`. Swagger: `@nestjs/swagger` (add decorators to new DTOs if the project uses them).
- Serving HTML: `@nestjs/serve-static` (`ServeStaticModule`), a view engine (`app.setViewEngine('hbs')`, `@Render()` controllers), or nothing (API only; look for `frontend/`, `web/`, `apps/*` in a monorepo with `nest-cli.json` `projects`).
- i18n: `nestjs-i18n` (`src/i18n/<lang>/*.json`, `I18nModule.forRoot`), or none.
- Reverse proxy: `app.set('trust proxy', ...)` in `main.ts` and the deployment config (nginx/Traefik) decide whether the client IP is real.

## Legal pages
- API-only backend: add nothing for pages. The frontend's stack file describes the pages. Report which frontend repo/folder hosts them.
- Existing route takes priority: search first (`grep -rniE "privacy|policy|oferta|offer|terms" src public views`) and update that document; never create a duplicate policy page. Default `/legal/{privacy,offer,refund,requisites}` only when none exists.
- Backend serves its own static site: put the generated HTML into the folder `ServeStaticModule` already serves (for example `public/legal/<slug>.html`) and follow `static-html.md` for the page chrome.
- View engine (`hbs`, `ejs`, `pug`): add a template per document extending the existing layout, and a route in an existing or new `LegalController` with `@Get('legal/:slug') @Render('legal')`. Whitelist the slug (`privacy`, `offer`, `refund`, `requisites`, from the documents step); never build a file path from the raw parameter.
- Optional JSON endpoint for mobile apps or separate frontends (`GET /legal/:slug` returning the document text and `version`) only when the frontend asks for it; documents are static assets, not database content.

## Consent checkbox in forms
- Server side only; the box is unchecked by default in whichever client renders it. The field is `consentPd: boolean`, a separate field from "accept the offer/terms" (`acceptOffer`). Never default it to `true` in DTOs, Swagger examples, or seeds.
- When the knowledge pack says consent is required for this endpoint, reject the request without it; otherwise accept it as optional:
```ts
export class CreateLeadDto {
  // ...existing fields
  @IsBoolean() @Equals(true, { message: 'consentPd must be accepted' }) consentPd: boolean; // required form
  // optional form: @IsOptional() @IsBoolean() consentPd?: boolean;
}
```
- Confirm a `ValidationPipe` actually applies to this route: global (`app.useGlobalPipes(new ValidationPipe(...))` in `main.ts`) or per route (`@UsePipes(...)`, `@Body(new ValidationPipe())`); without one the decorators above enforce nothing. With `whitelist: true` the field must be declared in the DTO or it is stripped. With `nestjs-zod` use `z.literal(true)` for the required case.
- After the request succeeds, record the consent through `ConsentService.record(...)` below, in the same handler or service transaction (so a missing log entry fails the request, not the other way around).

## Analytics gated by consent
Counters live in the frontend; see its stack file. On the backend:
- Do not add server-side analytics calls (Measurement Protocol, Metrica offline conversions, pixel webhooks) that run before the consent is on record. Gate them on the latest `grant` row for the subject.
- Templates rendered by NestJS (`hbs`/`ejs`) that contain counter snippets: wrap them in a flag passed from the controller and use the plain-JS loader from `static-html.md` instead of inline snippets.
- Do not set analytics cookies from interceptors or middleware.

## Consent banner
Not applicable in an API-only backend; the banner belongs to the frontend stack. For server-rendered templates (Accept all sets `analytics` and `marketing`, Reject sets neither, a Settings view has two separate unchecked toggles), copy the markup and `consent.js` from `static-html.md` into the existing layout template and use the project's CSS classes and tokens; bumping `data-version` invalidates the stored choice and reopens the banner. Texts come from `nestjs-i18n` keys or the template's existing translation helper.

## Consent log (existing backend only)
Only with an existing database and ORM from Detect. NEVER introduce a new database, ORM or migration tool. No ORM: report the gap. The log is append-only: the service exposes only `record`; there is no update or delete route, and no admin edit.
Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android` (the DTO below). Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
```ts
// consent/consent-log.entity.ts (TypeORM)
@Entity('consent_log') @Index(['subjectId', 'createdAt'])
export class ConsentLog {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column({ name: 'subject_id' }) subjectId: string;           // user id, else anonymous UUID from the client
  @CreateDateColumn({ name: 'created_at' }) createdAt: Date;   // UTC: use timestamptz on Postgres, driver option timezone 'Z' on MySQL
  @Column({ name: 'consent_version' }) consentVersion: string;
  @Column({ name: 'text_sha256', length: 64 }) textSha256: string;
  @Column() channel: 'web' | 'ios' | 'android';
  @Column({ name: 'form_id' }) formId: string;
  @Column({ type: 'varchar', nullable: true }) ip: string | null;
  @Column({ name: 'user_agent', type: 'text', nullable: true }) userAgent: string | null;
  @Column() action: 'grant' | 'revoke';
}
```
```ts
// consent/consent.controller.ts
export class RecordConsentDto {
  @IsString() @MaxLength(128) subjectId: string;
  @IsString() @MaxLength(32) consentVersion: string;
  @IsIn(['web', 'ios', 'android']) channel: 'web' | 'ios' | 'android';
  @IsString() @MaxLength(64) formId: string;
  @IsIn(['grant', 'revoke']) action: 'grant' | 'revoke';
}
@Controller('consents')
export class ConsentController {
  constructor(private readonly consents: ConsentService) {}
  @Post() @HttpCode(204)
  async record(@Body() dto: RecordConsentDto, @Ip() ip: string, @Headers('user-agent') ua?: string) {
    await this.consents.record({ ...dto, ip, userAgent: ua ?? null });
  }
}
```
- `ConsentService.record` looks up the text for `consentVersion` in a constants map (the same text the client rendered), throws `BadRequestException` for an unknown version, computes `createHash('sha256')` server-side, then `repo.insert(...)`. Never trust a client-supplied hash.
- Register `TypeOrmModule.forFeature([ConsentLog])`, the service, and the controller in a `ConsentModule` imported by `AppModule`. Prisma: add the model from `nextjs.md` to `schema.prisma`, with its `@map` column names and `@@map("consent_log")`, and use the existing `PrismaService`; other ORMs: same columns, insert-only, table `consent_log`.
- Never apply a migration. Create the migration file with the project's tool (`typeorm migration:generate`, `prisma migrate dev --create-only --name add_consent_log`, ...) only when the database host configured in the project is `localhost`, `127.0.0.1`, `::1` or a local socket ([ui-integration.md](../workflow/ui-integration.md#consent-log)); otherwise the command goes to «Сделать вам». Do not enable `synchronize: true`. When the tool may not run (non-local host, dependencies not installed), a Prisma migration may be written by hand as `prisma/migrations/<YYYYMMDDHHMMSS>_add_consent_log/migration.sql` matching the model; a TypeORM one is not: leave the command for the owner.
```sql
-- prisma/migrations/<YYYYMMDDHHMMSS>_add_consent_log/migration.sql: the ConsentLog model from nextjs.md on PostgreSQL,
-- with Prisma's default names (<table>_pkey, <table>_<columns>_idx); a new folder also needs migration_lock.toml
-- with provider = "postgresql". Another provider: leave `prisma migrate dev --create-only` to the owner.
-- CreateTable
CREATE TABLE "consent_log" (
    "id" TEXT NOT NULL,
    "subject_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "consent_version" TEXT NOT NULL,
    "text_sha256" TEXT NOT NULL,
    "channel" TEXT NOT NULL,
    "form_id" TEXT NOT NULL,
    "ip" TEXT,
    "user_agent" TEXT,
    "action" TEXT NOT NULL,

    CONSTRAINT "consent_log_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "consent_log_subject_id_created_at_idx" ON "consent_log"("subject_id", "created_at");
```
- IP is only trustworthy behind a correctly configured proxy: with Express use `app.set('trust proxy', ...)` as the deployment requires and keep `@Ip()`; do not parse `X-Forwarded-For` by hand. Add rate limiting (`@nestjs/throttler`) only if the project already uses it.
- Authenticated subjects: take `subjectId` from the auth guard, not from the body.

## Footer and links
No footer on an API. If the backend sends emails (`@nestjs-modules/mailer`, `nodemailer`), add the Политика / Оферта / Возврат / Реквизиты links to the existing email layout template, using absolute URLs from config.

## i18n
- `nestjs-i18n`: add keys to `src/i18n/ru/*.json` and `en/*.json` (for example a `consent.json` with `required` and `translationNotice`); resolve with `i18n.t('consent.required', { lang })`.
- Validation messages from DTOs: keep the existing pattern (`i18nValidationMessage`) if present.
- RU strings and documents are authoritative. EN versions are translations and carry a `translationNotice` key. No i18n library: keep messages in one constants file.

## Verify and record state
- `npm run build` (`nest build`), `npm run lint`, `npx tsc --noEmit -p tsconfig.json`, `npm test`, `npm run test:e2e` if the project has them. Add a unit test next to the new service: unknown version rejected, hash stable, no update/delete method exposed.
- Start the app locally and `curl -i -X POST localhost:3000/consents -H 'content-type: application/json' -d '{...}'` against a local dev database where the owner has applied the migration (never apply it yourself): expect 204, then a row with UTC time, hash, IP and user agent.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
