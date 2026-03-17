const mongoose = require("mongoose");
const bcrypt = require("bcryptjs");

const UserSchema = new mongoose.Schema(
  {
    // -------- Auth fields --------
    title: String,
    name: { type: String, required: true },
    surname: { type: String, required: true },
    email: { type: String, required: true, unique: true },
    country: String,
    phone: String,
    password: { type: String, required: true },
    role: {
      type: String,
      enum: ["recruiter", "candidate"],
      default: "candidate",
    },

    // ✅ First-time profile completion flag
    profileCompleted: {
      type: Boolean,
      default: false,
      required: true,
    },

    // -------- Profile common --------
    profileType: {
      type: String,
      enum: ["student", "professional"],
      default: "student",
    },

    profilePhoto: { type: String, default: "" },
    resume: { type: String, default: "" },

    linkedinUrl: { type: String, default: "" },
    githubUrl: { type: String, default: "" },

    skills: { type: [String], default: [] },

    // -------- Student fields --------
    educationStatus: { type: String, default: "" },
    college: { type: String, default: "" },
    degree: { type: String, default: "" },
    specialization: { type: String, default: "" },
    graduationYear: { type: String, default: "" },
    city: { type: String, default: "" },
    extraInfo: { type: String, default: "" },

    // -------- Professional fields --------
    jobStatus: { type: String, default: "" },
    experience: { type: String, default: "" },
    company: { type: String, default: "" },
    jobRole: { type: String, default: "" },
  },
  { timestamps: true }
);

// 🔐 Password hashing (SAFE)
// 🔐 Password hashing (Mongoose v7+ safe)
UserSchema.pre("save", async function () {
  if (!this.isModified("password")) return;
  this.password = await bcrypt.hash(this.password, 10);
});


module.exports = mongoose.model("User", UserSchema);
