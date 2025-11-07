# Digital Signature Stamp - Deployment Checklist

Use this checklist to ensure a smooth deployment of the digital signature stamp system.

---

## Pre-Deployment

### 1. Review Changes
- [ ] Read `IMPLEMENTATION_SUMMARY.md`
- [ ] Review `DIGITAL_SIGNATURE_STAMP_README.md`
- [ ] Understand what the migrations do
- [ ] Review modified files:
  - [ ] `Inventory/models.py`
  - [ ] `Inventory/signals.py`
- [ ] Review new migration files:
  - [ ] `0014_add_signature_stamp_to_profile.py`
  - [ ] `0015_backfill_signature_stamps.py`

### 2. Backup Everything
- [ ] **CRITICAL:** Backup production database
  ```bash
  # PostgreSQL
  pg_dump -U username -d database_name > backup_$(date +%Y%m%d_%H%M%S).sql
  
  # SQLite
  cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)
  ```
- [ ] Verify backup is complete and valid
- [ ] Store backup in safe location
- [ ] Document backup location and timestamp

### 3. Test Environment Setup
- [ ] Create a copy of production database
- [ ] Set up test environment with database copy
- [ ] Verify test environment is working

---

## Testing Phase

### 4. Test on Copy First
- [ ] Apply migrations to test database
  ```bash
  python manage.py migrate Inventory 0014_add_signature_stamp_to_profile
  python manage.py migrate Inventory 0015_backfill_signature_stamps
  ```
- [ ] Verify no errors during migration
- [ ] Check migration output for statistics
- [ ] Verify stamps were created:
  ```python
  from Inventory.models import Profile
  Profile.objects.filter(signature_stamp__isnull=False).count()
  ```

### 5. Test Functionality
- [ ] Create a new test user
- [ ] Verify profile is auto-created
- [ ] Verify stamp is auto-generated
- [ ] Test `get_or_create_signature_stamp()` method
- [ ] Test `display_signature_stamp()` method
- [ ] Test in Django admin
- [ ] Check application logs for errors

### 6. Test Rollback (Optional)
- [ ] Test rolling back migrations
  ```bash
  python manage.py migrate Inventory 0013_add_consignment_number
  ```
- [ ] Verify rollback works
- [ ] Restore test database from backup
- [ ] Re-apply migrations

---

## Production Deployment

### 7. Pre-Deployment Checks
- [ ] All tests passed in test environment
- [ ] Backup verified and accessible
- [ ] Rollback procedure documented
- [ ] Deployment window scheduled (low traffic time)
- [ ] Team notified of deployment
- [ ] Monitoring tools ready

### 8. Code Deployment
- [ ] Pull latest code to production server
  ```bash
  git pull origin main
  ```
- [ ] Verify all files are present:
  - [ ] Modified: `Inventory/models.py`
  - [ ] Modified: `Inventory/signals.py`
  - [ ] New: `migrations/0014_add_signature_stamp_to_profile.py`
  - [ ] New: `migrations/0015_backfill_signature_stamps.py`

### 9. Apply Migrations
- [ ] Put application in maintenance mode (if applicable)
- [ ] Apply schema migration:
  ```bash
  python manage.py migrate Inventory 0014_add_signature_stamp_to_profile
  ```
- [ ] Verify success (should see "OK")
- [ ] Apply data migration:
  ```bash
  python manage.py migrate Inventory 0015_backfill_signature_stamps
  ```
- [ ] Review migration output statistics
- [ ] Check for any errors or warnings

### 10. Restart Services
- [ ] Restart Django application
  ```bash
  # Example for systemd
  sudo systemctl restart gunicorn
  
  # Or for development
  # Ctrl+C and restart: python manage.py runserver
  ```
- [ ] Verify application starts successfully
- [ ] Check no errors in startup logs

---

## Post-Deployment Verification

### 11. Immediate Verification
- [ ] Application is accessible
- [ ] No errors in logs
- [ ] Existing users can log in
- [ ] Existing functionality works

### 12. Stamp Verification
- [ ] Check stamps were created:
  ```python
  from Inventory.models import Profile
  total = Profile.objects.count()
  with_stamps = Profile.objects.filter(signature_stamp__isnull=False).count()
  print(f"Profiles: {total}, With stamps: {with_stamps}")
  ```
- [ ] Verify sample stamps look correct
- [ ] Check stamp format is correct

### 13. New User Test
- [ ] Create a new test user (via admin or registration)
- [ ] Verify profile is created automatically
- [ ] Verify stamp is generated automatically
- [ ] Check stamp format is correct
- [ ] Delete test user

### 14. Integration Testing
- [ ] Test user login
- [ ] Test profile page access
- [ ] Test any views that use profiles
- [ ] Test Django admin access to profiles
- [ ] Verify no 'NoneType' errors

### 15. Log Review
- [ ] Check application logs for:
  - [ ] Migration success messages
  - [ ] Stamp generation messages
  - [ ] Any warnings about profiles without users
  - [ ] Any errors
- [ ] Review Django logs:
  ```bash
  tail -f logs/django.log | grep "signature stamp"
  ```

---

## Monitoring (First 24-48 Hours)

### 16. Active Monitoring
- [ ] Monitor error logs continuously
- [ ] Watch for 'NoneType' errors (should be none)
- [ ] Monitor new user registrations
- [ ] Verify stamps are generated for new users
- [ ] Check database performance
- [ ] Monitor application response times

### 17. User Feedback
- [ ] Monitor support channels for issues
- [ ] Check for user-reported errors
- [ ] Document any unexpected behavior

---

## Rollback Plan (If Needed)

### 18. Rollback Procedure
If critical issues occur:

- [ ] Put application in maintenance mode
- [ ] Roll back migrations:
  ```bash
  python manage.py migrate Inventory 0013_add_consignment_number
  ```
- [ ] Restore database from backup (if necessary):
  ```bash
  # PostgreSQL
  psql -U username -d database_name < backup_file.sql
  
  # SQLite
  cp db.sqlite3.backup db.sqlite3
  ```
- [ ] Restart application
- [ ] Verify application works
- [ ] Notify team
- [ ] Document issues for investigation

---

## Documentation Updates

### 19. Update Documentation
- [ ] Document deployment date and time
- [ ] Document any issues encountered
- [ ] Update runbook with lessons learned
- [ ] Share knowledge with team

---

## Success Criteria

Deployment is successful when:

- [x] ✅ Migrations applied without errors
- [x] ✅ Existing users have signature stamps
- [x] ✅ New users automatically get stamps
- [x] ✅ No 'NoneType' errors in logs
- [x] ✅ Application functions normally
- [x] ✅ All tests pass
- [x] ✅ No user-reported issues

---

## Post-Deployment Tasks

### 20. Cleanup and Optimization
- [ ] Remove test users created during verification
- [ ] Archive deployment logs
- [ ] Update monitoring dashboards (if applicable)
- [ ] Schedule follow-up review (1 week)

### 21. Team Communication
- [ ] Notify team of successful deployment
- [ ] Share deployment summary
- [ ] Document any lessons learned
- [ ] Update team wiki/documentation

---

## Troubleshooting Reference

### If migrations fail:
1. Check database connectivity
2. Review migration file for syntax errors
3. Check database user permissions
4. Review error logs
5. Consult `DIGITAL_SIGNATURE_STAMP_README.md` troubleshooting section

### If stamps not generated:
1. Restart Django server (reload signals)
2. Check signals are imported in `apps.py`
3. Manually generate: `profile.get_or_create_signature_stamp()`
4. Check logs for errors

### If 'NoneType' errors occur:
1. Check which profile is causing the issue
2. Verify profile has a user
3. Verify user has a username
4. Check signal error handling is working
5. Review logs for details

---

## Emergency Contacts

- **Database Admin:** [Name/Contact]
- **DevOps Lead:** [Name/Contact]
- **Project Lead:** [Name/Contact]
- **On-Call Developer:** [Name/Contact]

---

## Notes Section

Use this space to document anything specific to your deployment:

**Deployment Date:** _______________

**Deployed By:** _______________

**Database Backup Location:** _______________

**Issues Encountered:**
- 
- 
- 

**Resolution:**
- 
- 
- 

**Additional Notes:**
- 
- 
- 

---

**Checklist Version:** 1.0.0  
**Last Updated:** November 6, 2024  
**Status:** Ready for Use
