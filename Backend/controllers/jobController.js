const Job = require("../models/Job");

/**
 * @route   POST /api/jobs
 * @desc    Recruiter posts a new job
 * @access  Private (Recruiter)
 */
const createJob = async (req, res) => {
  try {
    // recruiter id comes from authMiddleware

    //test
    console.log("🔥 CREATE JOB HIT");
    console.log("User:", req.user?._id);
    console.log("Body:", req.body);
    //test
    const recruiterId = req.user.id;
    const {
      title,
      description,
      location,
      employmentType,
      minSalary,
      maxSalary,
      skills,
      aiQuestions,
    } = req.body;

    const job = await Job.create({
      recruiter: recruiterId,
      title,
      description,
      location,
      employmentType,
      salary: {
        min: minSalary,
        max: maxSalary,
      },
      skills,
      aiQuestions,
    });

    res.status(201).json({
      success: true,
      message: "Job posted successfully",
      job,
    });
  } catch (error) {
    console.error("Error creating job:", error);
    res.status(500).json({
      success: false,
      message: "Server error while posting job",
    });
  }
};

/**
 * @route   GET /api/jobs/my
 * @desc    Get all jobs posted by logged-in recruiter
 * @access  Private (Recruiter)
 */
const getMyJobs = async (req, res) => {
  try {
    const recruiterId = req.user.id;

    const jobs = await Job.find({ recruiter: recruiterId }).sort({
      createdAt: -1,
    });

    res.status(200).json({
      success: true,
      jobs,
    });
  } catch (error) {
    console.error("Error fetching recruiter jobs:", error);
    res.status(500).json({
      success: false,
      message: "Server error while fetching jobs",
    });
  }
};

/**
 * @route   GET /api/jobs
 * @desc    Get all active jobs (for candidates)
 * @access  Public
 */
const getAllJobs = async (req, res) => {
  try {
    const jobs = await Job.find({}).sort({ createdAt: -1 });

    res.status(200).json({
      success: true,
      jobs,
    });
  } catch (error) {
    console.error("Error fetching all jobs:", error);
    res.status(500).json({
      success: false,
      message: "Server error while fetching jobs",
    });
  }
};

/**
 * @route   PUT /api/jobs/:id
 * @desc    Update a job posted by recruiter
 * @access  Private (Recruiter)
 */
const updateJob = async (req, res) => {
  try {
    const recruiterId = req.user.id;
    const jobId = req.params.id;

    const {
      title,
      description,
      location,
      employmentType,
      minSalary,
      maxSalary,
      skills,
      aiQuestions,
    } = req.body;

    const job = await Job.findById(jobId);

    if (!job) {
      return res.status(404).json({
        success: false,
        message: "Job not found",
      });
    }

    // Ensure recruiter owns this job
    if (job.recruiter.toString() !== recruiterId) {
      return res.status(403).json({
        success: false,
        message: "Not authorized to update this job",
      });
    }

    job.title = title || job.title;
    job.description = description || job.description;
    job.status = "Active";
    job.location = location || job.location;
    job.employmentType = employmentType || job.employmentType;
    job.salary = {
      min: minSalary ?? job.salary?.min,
      max: maxSalary ?? job.salary?.max,
    };
    job.skills = skills ?? job.skills;
    job.aiQuestions = aiQuestions ?? job.aiQuestions;

    const updatedJob = await job.save();

    res.status(200).json({
      success: true,
      message: "Job updated successfully",
      job: updatedJob,
    });
  } catch (error) {
    console.error("Error updating job:", error);
    res.status(500).json({
      success: false,
      message: "Server error while updating job",
    });
  }
};

/**
 * @route   PATCH /api/jobs/:id/close
 * @desc    Close a job (set status to Closed)
 * @access  Private (Recruiter)
 */
const closeJob = async (req, res) => {
  try {
    const recruiterId = req.user.id;
    const jobId = req.params.id;

    const job = await Job.findById(jobId);

    if (!job) {
      return res.status(404).json({
        success: false,
        message: "Job not found",
      });
    }

    if (job.recruiter.toString() !== recruiterId) {
      return res.status(403).json({
        success: false,
        message: "Not authorized to close this job",
      });
    }

    job.status = "Closed";

    const updatedJob = await job.save();

    res.status(200).json({
      success: true,
      message: "Job closed successfully",
      job: updatedJob,
    });
  } catch (error) {
    console.error("Error closing job:", error);
    res.status(500).json({
      success: false,
      message: "Server error while closing job",
    });
  }
};

module.exports = {
  createJob,
  getMyJobs,
  getAllJobs,
  updateJob,
  closeJob,
};
