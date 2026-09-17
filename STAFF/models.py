from django.db import models

GENDER_CHOICES = [
    ('M', 'Male'),
    ('F', 'Female'),
    ('O', 'Other'),
]
STAFF_ROLE = [
    ('FOUNDER','Founder'),
    ('CO-FOUNDER', 'Co-Founder'),
    ('SNR-JOURNALIST', 'Snr-Journalist'),
    ('JOURNALIST', 'Journalist'),
]


class StaffProfile(models.Model):
    auth = models.ForeignKey("AUTHENTICATION.Auth", on_delete=models.CASCADE)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    full_name = models.CharField(max_length=100, blank=True)
    twitter_handle = models.URLField(blank=True, null=True)
    whatsapp_handle = models.URLField(blank=True, null=True)
    facebook_handle = models.URLField(blank=True, null=True)
    # subsequent handle can be added in the future
    speciality = models.JSONField(default=list, blank=True, null=True)    #   IF THE STAFF HAVE A SPECIAL NICHE ABOUT POST THEY LOVE MAKING
    bio = models.TextField(blank=True, default="")
    role = models.CharField(max_length=20, choices=STAFF_ROLE, blank=True, default="JOURNALIST")
    tribute_bio = models.TextField(blank=True, null=True)    #   DIFFERENT FROM BIO AS THIS ONE, THE ADMIN WRITE IT FOR THE STAFF
    last_promotion = models.DateField(blank=True, null=True)  #   DIFFERENT FROM THEN THEY CREATED ACCOUNT, THIS CAN BE USED TO SHOW THEY HAVE BEEN PROMOTED WITHING A TIME SPA
    get_blog_notification = models.BooleanField(default=True) #   WETHER TO BEEP THE STAFF WHEN THEIR BLOG GET VIEWWED

    class Meta:
        verbose_name = "Staff profile"
        verbose_name_plural = "Staff profiles"

    def __str__(self):
        return f"{self.auth.email} + {self.full_name}"


class FollowRelationship(models.Model):
    """Track who follows which staff profile and when the relationship started."""

    follower = models.ForeignKey("STAFF.StaffProfile", on_delete=models.CASCADE, related_name="following")
    followee = models.ForeignKey("STAFF.StaffProfile", on_delete=models.CASCADE, related_name="followers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "followee"], name="unique_staff_follow_relation")
        ]

    def __str__(self):
        return f"{self.follower} follows {self.followee}"